#!/usr/bin/env python3
"""Factudio backend.

A small stdlib-only HTTP server that wraps the Factorio harness for the
``studio/`` web app. Boots on 127.0.0.1 only -- no network exposure.

Endpoints
---------

    GET  /                       -> studio/index.html (and static assets)
    GET  /api/health             -> {ok, harness, library_root, mods_enabled}
    GET  /api/recipes            -> [{name, category, results, ingredients, from_mod}, ...]
    GET  /api/machines           -> [{name, crafting_categories, energy_source, ...}, ...]
    GET  /api/belts              -> [{name, items_per_second_total, ...}, ...]
    GET  /api/items              -> [{name, from_mod, place_result, ...}, ...]
    GET  /api/quality            -> [{name, level, ...}, ...]
    GET  /api/research           -> ["mining-productivity", "worker-robots-speed", ...]
    GET  /api/library            -> [{name, label, kind, sizes}, ...]
    POST /api/synthesize         <- BuildSpec JSON
                                 -> {blueprint_string, report_md, warnings, rates,
                                     mod_compat}
    POST /api/validate           <- {string}
                                 -> {decoded, warnings, rates, mod_compat}
    POST /api/save               <- {string, name?}
                                 -> {ok, path}

Run::

    python3 tools/studio_server.py --port 8766

The server refuses to bind to anything other than 127.0.0.1 to avoid
accidentally exposing the synthesis pipeline to the network.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import socket
import socketserver
import sys
import threading
import time
import traceback
from dataclasses import asdict, fields, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
STUDIO_DIR = REPO_ROOT / "studio"
SPECS_DIR = REPO_ROOT / "specs"
LIBRARY_DIR = REPO_ROOT / "library" / "personal"
MOD_LIST = Path.home() / ".factorio" / "mods" / "mod-list.json"

# Make `harness` and `tools` packages importable when running from anywhere.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))


# ---------------------------------------------------------------------------
# Lazy harness imports.
# ---------------------------------------------------------------------------

_harness_mod: Any = None
_harness_err: str | None = None


def _harness():
    """Import the harness on demand so a partial install still serves /api/recipes."""
    global _harness_mod, _harness_err
    if _harness_mod is not None or _harness_err is not None:
        return _harness_mod
    try:
        import harness  # noqa: WPS433
        from harness import spec as spec_mod  # noqa: WPS433
        _harness_mod = (harness, spec_mod)
    except Exception as e:  # pragma: no cover
        _harness_err = f"{type(e).__name__}: {e}"
        _harness_mod = None
    return _harness_mod


def _mod_compat_module():
    """Lazy-load harness.mod_compat. Returns None if unavailable."""
    try:
        from harness import mod_compat  # noqa: WPS433
        return mod_compat
    except Exception:
        return None


def _library_store():
    from blueprint_storage import LibraryStore  # noqa: WPS433
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    return LibraryStore(LIBRARY_DIR)


def _blueprint_codec():
    import blueprint_codec  # noqa: WPS433
    return blueprint_codec


def _rate_calculator():
    """Lazy import; returns the module."""
    import rate_calculator  # noqa: WPS433
    return rate_calculator


# ---------------------------------------------------------------------------
# Spec catalogs (cached in memory; cheap; specs/ is small).
# ---------------------------------------------------------------------------

_SPEC_CACHE: dict[str, Any] = {}


def _load_spec(name: str) -> Any:
    if name not in _SPEC_CACHE:
        _SPEC_CACHE[name] = json.loads((SPECS_DIR / name).read_text())
    return _SPEC_CACHE[name]


def _enabled_mods() -> list[str]:
    """Read ~/.factorio/mods/mod-list.json. Empty list if not present."""
    try:
        data = json.loads(MOD_LIST.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    out: list[str] = []
    for m in data.get("mods", []):
        if m.get("enabled"):
            out.append(m["name"])
    return out


def _recipe_categories_inverted() -> dict[str, set[str]]:
    """Recipe-category -> set(machines) lookup."""
    raw = _load_spec("recipe_categories.json")
    return {cat: set(machines) for cat, machines in (raw.get("crafting_categories") or {}).items()}


def _machines_that_craft(recipe_category: str) -> list[str]:
    table = _recipe_categories_inverted()
    return sorted(table.get(recipe_category, set()))


# ---------------------------------------------------------------------------
# Mod-compat checking.
# ---------------------------------------------------------------------------

def _mod_compat_for_target(target_item_name: str) -> dict[str, Any]:
    """Return {required, available, missing, warnings} for a target item.

    Walks the recipe graph one level: the target item's first matching recipe
    plus its ingredients. We *don't* recurse arbitrarily deep -- the goal is
    to tell the user "this build needs Space Age" without traversing the
    whole tree.
    """
    items = {it["name"]: it for it in _load_spec("items.json")}
    recipes = _load_spec("recipes.json")
    enabled = set(_enabled_mods())

    required: set[str] = set()

    item = items.get(target_item_name)
    if item:
        m = item.get("from_mod")
        if m:
            required.add(m)

    # First non-recycling recipe whose result is target_item_name:
    chosen_recipe = None
    for r in recipes:
        if (r.get("category") or "").endswith("recycling"):
            continue
        for res in (r.get("results") or []):
            if res.get("name") == target_item_name:
                chosen_recipe = r
                break
        if chosen_recipe is not None:
            break

    if chosen_recipe is not None:
        m = chosen_recipe.get("from_mod")
        if m:
            required.add(m)
        for ing in (chosen_recipe.get("ingredients") or []):
            ing_item = items.get(ing.get("name"))
            if ing_item and ing_item.get("from_mod"):
                required.add(ing_item["from_mod"])

    # 'core' is always available; treat 'base' as always available too because
    # it's the vanilla bedrock and our specs only exist for installs that have
    # `base`. None means vanilla untagged.
    available = enabled | {"base", "core"}
    missing = sorted(m for m in required if m and m not in available)

    return {
        "required": sorted(required),
        "available": sorted(available),
        "missing": missing,
    }


def _suggest_substitute(missing_target: str) -> str | None:
    """Suggest a vanilla substitute for a modded entity/item name.

    First defers to `harness.mod_compat.vanilla_substitute` (the project-wide
    table). Falls back to a small studio-local table for items that aren't
    entities (so the harness module doesn't carry them).
    """
    mc = _mod_compat_module()
    if mc is not None:
        try:
            sub = mc.vanilla_substitute(missing_target)
            if sub:
                return sub
        except Exception:
            pass
    table = {
        "molten-iron": "iron-plate",
        "molten-copper": "copper-plate",
        "casting-iron": "iron-plate",
        "casting-copper": "copper-plate",
        "promethium-transport-belt": "turbo-transport-belt",
        "promethium-belt": "turbo-transport-belt",
    }
    return table.get(missing_target)


# ---------------------------------------------------------------------------
# Rate calculation helper for /api/synthesize and /api/validate.
# ---------------------------------------------------------------------------

def _rates_summary_for_spec(spec_dict: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort RateCalculator summary for a synthesis spec.

    Returns {} on failure; the caller should treat that as "rates skipped".
    """
    try:
        rc = _rate_calculator()
    except Exception:  # pragma: no cover
        return None

    target = spec_dict.get("target")
    machine = spec_dict.get("machine_choice")
    if not target or not machine:
        return None

    # Find a sensible non-recycling recipe for `target` whose category is
    # craftable by `machine`.
    recipes = _load_spec("recipes.json")
    rc_table = _recipe_categories_inverted()
    chosen = None
    for r in recipes:
        if (r.get("category") or "").endswith("recycling"):
            continue
        if not any(res.get("name") == target for res in (r.get("results") or [])):
            continue
        cat = r.get("category")
        if cat in rc_table and machine in rc_table[cat]:
            chosen = r
            break
    if chosen is None:
        return None

    machine_count = int(spec_dict.get("machine_count") or 1)
    quality = spec_dict.get("quality") or "normal"
    research = spec_dict.get("research_levels") or {}

    try:
        result = rc.compute_rates(rc.RateInput(
            recipe=chosen["name"],
            machine=machine,
            machine_quality=quality,
            machine_count=machine_count,
            research_levels=research,
        ))
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}

    # Strip dataclasses to a small JSON-shaped summary (the full result is
    # big and contains nested dicts already).
    return {
        "recipe": chosen["name"],
        "machine": machine,
        "machine_count": machine_count,
        "crafts_per_second_per_machine": result.crafts_per_second_per_machine,
        "crafts_per_second_total": result.crafts_per_second_total,
        "inputs_per_second": result.inputs_per_second,
        "outputs_per_second": result.outputs_per_second,
        "power_kw_per_machine": result.power_kw_per_machine,
        "power_kw_total": result.power_kw_total,
        "pollution_per_minute_total": result.pollution_per_minute_total,
        "diagnostics": result.diagnostics,
    }


# ---------------------------------------------------------------------------
# BuildSpec construction from JSON request body.
# ---------------------------------------------------------------------------

def _spec_from_payload(payload: dict[str, Any]):
    """Coerce a JSON payload into a `BuildSpec` dataclass instance.

    Accepts arbitrary extra keys (ignored) and missing optional keys
    (default values used).
    """
    h = _harness()
    if h is None:
        raise RuntimeError(f"harness unavailable: {_harness_err}")
    _harness_pkg, spec_mod = h
    BuildSpec = spec_mod.BuildSpec

    valid_fields = {f.name for f in fields(BuildSpec)}
    cleaned = {k: v for k, v in payload.items() if k in valid_fields}
    return BuildSpec(**cleaned)


# ---------------------------------------------------------------------------
# Catalog endpoints (light shape massage so the front-end can render fast).
# ---------------------------------------------------------------------------

def _api_recipes() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in _load_spec("recipes.json"):
        out.append({
            "name": r["name"],
            "category": r.get("category"),
            "from_mod": r.get("from_mod"),
            "ingredients": r.get("ingredients") or [],
            "results": r.get("results") or [],
            "energy_required": r.get("energy_required"),
            "allow_productivity": r.get("allow_productivity", True),
        })
    return out


def _api_machines() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _load_spec("machines.json"):
        es = (m.get("energy_source") or {})
        out.append({
            "name": m["name"],
            "type": m.get("type"),
            "from_mod": m.get("from_mod"),
            "crafting_categories": m.get("crafting_categories") or [],
            "crafting_speed": m.get("crafting_speed"),
            "energy_source_type": es.get("type"),
            "energy_usage_kw": m.get("energy_usage_kw"),
            "module_slots": m.get("module_slots"),
            "tile_size": m.get("tile_size"),
        })
    return out


def _api_belts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in _load_spec("belts.json"):
        # Only true belts (not splitters/underground) for the dropdown.
        if b.get("type") != "transport-belt":
            continue
        out.append({
            "name": b["name"],
            "items_per_second_total": b.get("items_per_second_total"),
            "items_per_second_per_lane": b.get("items_per_second_per_lane"),
            "from_mod": b.get("from_mod"),
        })
    return out


def _api_items() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in _load_spec("items.json"):
        out.append({
            "name": i["name"],
            "from_mod": i.get("from_mod"),
            "place_result": i.get("place_result"),
            "subgroup": i.get("subgroup"),
            "fuel_category": i.get("fuel_category"),
            "fuel_value_kj": i.get("fuel_value_kj"),
        })
    return out


def _api_quality() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in _load_spec("quality.json"):
        out.append({
            "name": q["name"],
            "level": q.get("level"),
            "rank": q.get("rank"),
        })
    return sorted(out, key=lambda q: (q.get("level") or 0))


def _api_research() -> list[str]:
    """Distinct effect-types that look like the kind a planner cares about."""
    raw = json.loads((SPECS_DIR / "research_effects.json").read_text())
    seen: set[str] = set()
    for r in raw:
        et = r.get("effect_type")
        if et and et in {
            "mining-drill-productivity-bonus",
            "worker-robot-speed",
            "worker-robot-storage",
            "laboratory-speed",
            "laboratory-productivity",
            "follower-robot-count",
            "change-recipe-productivity",
            "inserter-stack-size-bonus",
        }:
            seen.add(et)
    return sorted(seen)


def _api_library() -> list[dict[str, Any]]:
    try:
        store = _library_store()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for entry in store.list():
        out.append({
            "name": entry.name,
            "kind": entry.kind,
            "label": entry.label,
            "description": entry.description,
            "sizes": entry.sizes,
            "path": str(entry.path.relative_to(REPO_ROOT)),
        })
    return out


# ---------------------------------------------------------------------------
# POST handlers.
# ---------------------------------------------------------------------------

def _api_synthesize(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("target")
    warnings: list[dict[str, Any]] = []

    mod_compat = _mod_compat_for_target(target) if target else {
        "required": [], "available": sorted(set(_enabled_mods()) | {"base", "core"}), "missing": [],
    }
    for m in mod_compat["missing"]:
        warnings.append({
            "level": "error",
            "message": f"target {target!r} requires mod {m!r} which is not enabled in mod-list.json",
            "suggested_substitute": _suggest_substitute(target),
        })

    try:
        spec = _spec_from_payload(payload)
        h = _harness()
        if h is None:
            return {
                "blueprint_string": None,
                "report_md": "",
                "warnings": warnings + [{"level": "error", "message": f"harness unavailable: {_harness_err}"}],
                "rates": None,
                "mod_compat": mod_compat,
            }
        harness_pkg, _ = h
        result = harness_pkg.synthesize(spec)
    except Exception as e:
        warnings.append({"level": "error", "message": f"synthesis failed: {e}"})
        return {
            "blueprint_string": None,
            "report_md": "",
            "warnings": warnings,
            "rates": _rates_summary_for_spec(payload),
            "mod_compat": mod_compat,
        }

    for w in result.warnings:
        warnings.append({"level": "warning", "message": w})

    return {
        "blueprint_string": result.blueprint_string,
        "entity_count": result.entity_count,
        "report_md": result.report,
        "warnings": warnings,
        "rates": _rates_summary_for_spec(payload),
        "mod_compat": mod_compat,
    }


def _api_validate(payload: dict[str, Any]) -> dict[str, Any]:
    string = (payload.get("string") or "").strip()
    if not string:
        return {"ok": False, "error": "missing 'string' in body"}

    codec = _blueprint_codec()
    try:
        decoded = codec.decode(string)
    except Exception as e:
        return {"ok": False, "error": f"decode failed: {e}"}

    # Re-encode for round-trip evidence (warning if mismatch).
    try:
        re_encoded = codec.encode(decoded)
        roundtrip_ok = (re_encoded == string)
    except Exception as e:  # pragma: no cover
        re_encoded = None
        roundtrip_ok = False

    body = decoded.get("blueprint") or decoded.get("blueprint_book") or {}

    # Use harness.mod_compat for a real attribution pass when available.
    mc = _mod_compat_module()
    mod_compat_payload: dict[str, Any]
    substitutes: dict[str, str] = {}
    if mc is not None:
        try:
            modset = mc.detect_user_mods()
            attribution = mc.attribute_blueprint(decoded)
            report = mc.check_compat(attribution.required_mods, modset, attribution=attribution)
            substitutes = dict(report.substitutes)
            mod_compat_payload = {
                "required": sorted(report.required),
                "available": sorted(report.enabled | report.required - (report.missing | report.disabled | report.zip_only)),
                "missing": sorted(report.missing),
                "disabled": sorted(report.disabled),
                "zip_only": sorted(report.zip_only),
                "substitutes": substitutes,
            }
        except Exception as e:  # pragma: no cover
            mod_compat_payload = {"required": [], "available": [], "missing": [], "error": str(e)}
    else:
        # Fallback: simple from_mod walk on items.json.
        items = {it["name"]: it for it in _load_spec("items.json")}
        enabled = set(_enabled_mods()) | {"base", "core"}
        required: set[str] = set()
        for ent in (body.get("entities") or []):
            nm = ent.get("name")
            item = items.get(nm)
            if item is None:
                for it in items.values():
                    if it.get("place_result") == nm:
                        item = it
                        break
            if item and item.get("from_mod"):
                required.add(item["from_mod"])
        mod_compat_payload = {
            "required": sorted(required),
            "available": sorted(enabled),
            "missing": sorted(m for m in required if m not in enabled),
        }

    warnings: list[dict[str, Any]] = []
    if not roundtrip_ok:
        warnings.append({"level": "warning",
                         "message": "blueprint string did not round-trip exactly (encode!=source); cosmetic differences only"})
    for ent_name, sub in substitutes.items():
        warnings.append({"level": "warning",
                         "message": f"entity {ent_name!r} from a missing mod; suggested vanilla substitute: {sub!r}",
                         "suggested_substitute": sub})

    return {
        "ok": True,
        "decoded": decoded,
        "entity_count": len(body.get("entities") or []),
        "label": body.get("label", ""),
        "roundtrip_ok": roundtrip_ok,
        "warnings": warnings,
        "mod_compat": mod_compat_payload,
    }


def _api_save(payload: dict[str, Any]) -> dict[str, Any]:
    string = (payload.get("string") or "").strip()
    name = payload.get("name")
    if not string:
        return {"ok": False, "error": "missing 'string' in body"}
    try:
        store = _library_store()
        path = store.add(string, name=name)
    except Exception as e:
        return {"ok": False, "error": f"save failed: {e}"}
    return {
        "ok": True,
        "path": str(path.relative_to(REPO_ROOT)),
        "name": path.stem,
    }


def _api_health() -> dict[str, Any]:
    return {
        "ok": True,
        "harness": _harness() is not None,
        "harness_error": _harness_err,
        "library_root": str(LIBRARY_DIR.relative_to(REPO_ROOT)),
        "mods_enabled_count": len(_enabled_mods()),
        "mod_list_present": MOD_LIST.exists(),
        "specs_dir_present": SPECS_DIR.exists(),
        "studio_dir_present": STUDIO_DIR.exists(),
    }


# ---------------------------------------------------------------------------
# HTTP plumbing.
# ---------------------------------------------------------------------------

ROUTES_GET: dict[str, Any] = {
    "/api/health": _api_health,
    "/api/recipes": _api_recipes,
    "/api/machines": _api_machines,
    "/api/belts": _api_belts,
    "/api/items": _api_items,
    "/api/quality": _api_quality,
    "/api/research": _api_research,
    "/api/library": _api_library,
}

ROUTES_POST: dict[str, Any] = {
    "/api/synthesize": _api_synthesize,
    "/api/validate": _api_validate,
    "/api/save": _api_save,
}


def _safe_static_path(url_path: str) -> Path | None:
    """Resolve `/<path>` against STUDIO_DIR. Refuses traversal."""
    rel = url_path.lstrip("/") or "index.html"
    candidate = (STUDIO_DIR / rel).resolve()
    try:
        candidate.relative_to(STUDIO_DIR.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "Factudio/0.1"

    # -- Helpers ---------------------------------------------------------

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str, ctype: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        ctype = _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- Logging ---------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        sys.stderr.write("[studio] " + fmt % args + "\n")

    # -- Verbs -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        url = urlparse(self.path)
        path = url.path
        # Health check should never block on a missing harness.
        if path in ROUTES_GET:
            try:
                payload = ROUTES_GET[path]()
            except Exception as e:  # pragma: no cover
                self._send_json(500, {"ok": False, "error": str(e), "trace": traceback.format_exc()})
                return
            self._send_json(200, payload)
            return

        # Static.
        candidate = _safe_static_path(path)
        if candidate is None:
            self._send_text(404, f"not found: {path}\n")
            return
        try:
            self._send_file(candidate)
        except Exception as e:  # pragma: no cover
            self._send_text(500, f"static read failed: {e}\n")

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        path = url.path
        handler = ROUTES_POST.get(path)
        if handler is None:
            self._send_text(404, f"no POST route: {path}\n")
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as e:
            self._send_json(400, {"ok": False, "error": f"invalid JSON body: {e}"})
            return
        try:
            response = handler(payload)
        except Exception as e:
            self._send_json(500, {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(),
            })
            return
        self._send_json(200, response)


class _ReuseTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


# ---------------------------------------------------------------------------
# Bind helpers.
# ---------------------------------------------------------------------------

def _safe_host(host: str) -> str:
    """Refuse to bind to anything other than loopback addresses."""
    h = (host or "").strip().lower()
    if h in {"127.0.0.1", "localhost", "::1"}:
        return "127.0.0.1"
    raise SystemExit(
        f"refusing to bind to {host!r}: studio_server only allows 127.0.0.1/localhost"
    )


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="studio_server",
        description="Factudio HTTP backend (Factorio Studio).",
    )
    parser.add_argument("--port", type=int, default=8766,
                        help="port to listen on (default: 8766)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="host to bind to (must be 127.0.0.1/localhost)")
    args = parser.parse_args(argv)

    host = _safe_host(args.host)
    port = args.port

    if not STUDIO_DIR.exists():
        print(f"warning: {STUDIO_DIR} does not exist; the GET / will 404 until you create it",
              file=sys.stderr)

    # Pre-import the harness so the first /api/synthesize isn't slow.
    h = _harness()
    if h is None:
        print(f"warning: harness import failed: {_harness_err}", file=sys.stderr)
    else:
        print("[studio] harness ready", file=sys.stderr)

    try:
        httpd = _ReuseTCPServer((host, port), StudioHandler)
    except OSError as e:
        print(f"bind failed on {host}:{port}: {e}", file=sys.stderr)
        return 2

    def _shutdown(*_a: Any) -> None:
        print("\n[studio] shutting down", file=sys.stderr)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print(f"[studio] listening on http://{host}:{port}/   (loopback only; ctrl-c to stop)",
          file=sys.stderr)
    print(f"[studio] static root: {STUDIO_DIR}", file=sys.stderr)
    print(f"[studio] library:     {LIBRARY_DIR}", file=sys.stderr)
    # Tight poll interval so Ctrl-C drops us in well under a second.
    httpd.serve_forever(poll_interval=0.1)
    httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
