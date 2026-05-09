#!/usr/bin/env python3
"""Inventory the user's Factorio blueprint library.

Walks every blueprint we can reach -- the binary
``~/.factorio/blueprint-storage-2.dat`` (best-effort, top-level only),
``library/personal/`` (decoded `.bp` files plus book directories), and
optionally ``library/external/<site>/`` (scraped reference blueprints) --
classifies each one, computes a throughput estimate when the recipe is
unambiguous, runs mod-compatibility, and writes both a machine-readable
JSON manifest and a human-readable Markdown digest to ``validation/``.

The goal is not to build a perfect catalog (the binary parser is
envelope-only; entity content is opaque without the in-game Export
string workflow). The goal is to surface every blueprint the user has,
flag what we know vs what we don't, and emit concrete validation
questions the user can answer to confirm the inventory.

Stdlib only.

CLI
---

    inventory_user_blueprints.py [--out validation/user_blueprint_inventory.md]
                                 [--manifest validation/user_blueprint_inventory.json]
                                 [--include-external]
                                 [--limit N]
                                 [--dat PATH]
                                 [--no-dat]

Outputs are written to ``validation/`` by default. ``--include-external``
adds the scraped library blueprints under ``library/external/<site>/``
to the inventory (off by default to keep the manifest focused on the
user's own work).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Bootstrap import paths (so we work whether invoked from the repo root or not)
# ---------------------------------------------------------------------------

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import blueprint_codec  # noqa: E402
import blueprint_storage_format as bsf  # noqa: E402
from blueprint_classifier import classify  # noqa: E402

# Mod compat / rate engine are optional: if `specs/*.json` is missing we
# downgrade gracefully rather than crashing.
try:
    from harness import mod_compat as _mod_compat  # noqa: E402
    _HAVE_MOD_COMPAT = True
except Exception:
    _mod_compat = None
    _HAVE_MOD_COMPAT = False

try:
    from tools.rate_calculator import RateInput, compute_rates  # noqa: E402
    from tools import rate_calculator as _rcalc  # noqa: E402
    _HAVE_RATES = True
except Exception:
    _HAVE_RATES = False
    _rcalc = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DAT = pathlib.Path.home() / ".factorio" / "blueprint-storage-2.dat"
DEFAULT_PERSONAL = ROOT / "library" / "personal"
DEFAULT_EXTERNAL = ROOT / "library" / "external"
DEFAULT_MANIFEST = ROOT / "validation" / "user_blueprint_inventory.json"
DEFAULT_DIGEST = ROOT / "validation" / "user_blueprint_inventory.md"


# ---------------------------------------------------------------------------
# Legacy entity rename map (1.x -> 2.0)
# Mirror of docs/legacy_entity_renames.md. If you change one, change the other.
# ---------------------------------------------------------------------------

LEGACY_RENAMES: dict[str, str] = {
    "logistic-chest-active-provider":  "active-provider-chest",
    "logistic-chest-passive-provider": "passive-provider-chest",
    "logistic-chest-storage":          "storage-chest",
    "logistic-chest-buffer":           "buffer-chest",
    "logistic-chest-requester":        "requester-chest",
    "stack-inserter":                  "bulk-inserter",
    "stack-filter-inserter":           "bulk-inserter",
    "filter-inserter":                 "fast-inserter",
}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class UnknownEntity:
    name: str
    count: int
    status: str                          # 'legacy_renamed' | 'unknown_entity'
    suggested_name: Optional[str] = None


@dataclass
class ThroughputEstimate:
    primary_recipe: str
    primary_machine: str
    items_per_second: float
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_recipe": self.primary_recipe,
            "primary_machine": self.primary_machine,
            "items_per_second": round(self.items_per_second, 6),
            "notes": self.notes,
        }


@dataclass
class InventoryRecord:
    id: str
    source: str
    label: str
    kind: str                            # 'blueprint' | 'blueprint-book' | 'envelope-only' | 'planner'
    string_size_bytes: int
    decoded: dict[str, Any]              # see _decoded_summary; '{}' for envelope-only
    purpose_guess: str
    purpose_confidence: str
    purpose_reasons: list[str]
    mod_compat: dict[str, list[str]]
    unknown_entities: list[UnknownEntity] = field(default_factory=list)
    throughput_estimate: Optional[ThroughputEstimate] = None
    validation_questions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "label": self.label,
            "kind": self.kind,
            "string_size_bytes": self.string_size_bytes,
            "decoded": self.decoded,
            "purpose_guess": self.purpose_guess,
            "purpose_confidence": self.purpose_confidence,
            "purpose_reasons": list(self.purpose_reasons),
            "mod_compat": dict(self.mod_compat),
            "unknown_entities": [
                {"name": u.name, "count": u.count,
                 "status": u.status, "suggested_name": u.suggested_name}
                for u in self.unknown_entities
            ],
            "throughput_estimate": self.throughput_estimate.to_dict() if self.throughput_estimate else None,
            "validation_questions": list(self.validation_questions),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Decoding helpers
# ---------------------------------------------------------------------------

def _kind_of(decoded: dict[str, Any]) -> str:
    for k in ("blueprint", "blueprint_book",
              "deconstruction_planner", "upgrade_planner"):
        if k in decoded:
            return k.replace("_", "-")
    return "unknown"


def _label_of(decoded: dict[str, Any]) -> str:
    for k in ("blueprint", "blueprint_book",
              "deconstruction_planner", "upgrade_planner"):
        body = decoded.get(k)
        if isinstance(body, dict):
            return body.get("label") or ""
    return ""


def _walk_entities(obj: Any):
    if isinstance(obj, dict):
        if "entities" in obj and isinstance(obj["entities"], list):
            for e in obj["entities"]:
                if isinstance(e, dict):
                    yield e
        for v in obj.values():
            yield from _walk_entities(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_entities(it)


def _walk_tiles(obj: Any):
    if isinstance(obj, dict):
        if "tiles" in obj and isinstance(obj["tiles"], list):
            for t in obj["tiles"]:
                if isinstance(t, dict):
                    yield t
        for v in obj.values():
            yield from _walk_tiles(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_tiles(it)


def _entity_counts(decoded: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in _walk_entities(decoded):
        n = e.get("name")
        if n:
            counts[n] = counts.get(n, 0) + 1
    return counts


def _bbox(decoded: dict[str, Any]) -> dict[str, int]:
    xs: list[float] = []
    ys: list[float] = []
    for e in _walk_entities(decoded):
        pos = e.get("position") or {}
        if "x" in pos and "y" in pos:
            xs.append(float(pos["x"]))
            ys.append(float(pos["y"]))
    if not xs:
        return {"width": 0, "height": 0}
    return {
        "width": int(round(max(xs) - min(xs))) + 1,
        "height": int(round(max(ys) - min(ys))) + 1,
    }


def _icons(decoded: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for k in ("blueprint", "blueprint_book",
              "deconstruction_planner", "upgrade_planner"):
        body = decoded.get(k)
        if isinstance(body, dict):
            for ic in body.get("icons") or []:
                sig = ic.get("signal") if isinstance(ic, dict) else None
                if isinstance(sig, dict) and sig.get("name"):
                    out.append(sig["name"])
    return out


def _version_packed(decoded: dict[str, Any]) -> Optional[int]:
    for k in ("blueprint", "blueprint_book",
              "deconstruction_planner", "upgrade_planner"):
        body = decoded.get(k)
        if isinstance(body, dict) and "version" in body:
            try:
                return int(body["version"])
            except (TypeError, ValueError):
                return None
    return None


def _summarise_decoded(decoded: dict[str, Any]) -> dict[str, Any]:
    counts = _entity_counts(decoded)
    tile_counts: dict[str, int] = {}
    for t in _walk_tiles(decoded):
        n = t.get("name")
        if n:
            tile_counts[n] = tile_counts.get(n, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    fluid_systems = sum(
        1 for e in _walk_entities(decoded)
        if "pipe" in e.get("name", "") or "tank" in e.get("name", "")
        or "pump" in e.get("name", "")
    )
    circuit = sum(
        1 for e in _walk_entities(decoded)
        if e.get("connections") or e.get("circuit_connections")
        or e.get("control_behavior")
    )
    return {
        "entity_count": sum(counts.values()),
        "tile_count": sum(tile_counts.values()),
        "bbox": _bbox(decoded),
        "top_entities": [list(t) for t in top],
        "fluid_systems": fluid_systems,
        "circuit_networks": circuit,
        "icons": _icons(decoded),
        "version_packed": _version_packed(decoded),
    }


# ---------------------------------------------------------------------------
# Mod attribution + unknown-entity / legacy-rename detection
# ---------------------------------------------------------------------------

def _mod_compat_for(decoded: dict[str, Any]
                    ) -> tuple[dict[str, list[str]], list[UnknownEntity]]:
    """Run mod_compat over a decoded blueprint and post-process unknowns
    against the legacy-rename table. Returns (mod_compat_dict, unknowns).

    If `harness.mod_compat` is unavailable we return a minimal record
    saying so.
    """
    if not _HAVE_MOD_COMPAT:
        return (
            {"required_mods": [], "enabled": [], "disabled": [],
             "missing": [], "zip_only": [], "substitutes_available": [],
             "policy": "unavailable (harness.mod_compat not importable)"},
            [],
        )

    modset = _mod_compat.detect_user_mods()
    attr = _mod_compat.attribute_blueprint(decoded)
    compat = _mod_compat.check_compat(
        attr.required_mods, modset, attribution=attr,
        mod_set_policy="user-any",
    )

    # Process unknown entities through the legacy-rename table.
    unknowns: list[UnknownEntity] = []
    for u in compat.unknown_entities:
        if u.kind != "entity":
            # Unknown recipes/items become flag-as-is for now; they don't
            # usually break a paste.
            continue
        modern = LEGACY_RENAMES.get(u.name)
        if modern:
            unknowns.append(UnknownEntity(
                name=u.name, count=u.count,
                status="legacy_renamed", suggested_name=modern,
            ))
        else:
            unknowns.append(UnknownEntity(
                name=u.name, count=u.count, status="unknown_entity",
            ))

    out = {
        "required_mods": sorted(compat.required),
        "enabled": sorted(compat.enabled),
        "disabled": sorted(compat.disabled),
        "missing": sorted(compat.missing),
        "zip_only": sorted(compat.zip_only),
        "substitutes_available": sorted(
            f"{k} -> {v}" for k, v in compat.substitutes.items()
        ),
        "policy": "user-any",
    }
    return out, unknowns


# ---------------------------------------------------------------------------
# Throughput estimate
# ---------------------------------------------------------------------------

# Map a producer entity (the one we see in the blueprint) to a sensible
# default machine name for the rate calculator. The user's actual install
# may use a different overlay; we pick a vanilla baseline that's safe.
_MACHINE_DEFAULTS = {
    "stone-furnace": "stone-furnace",
    "steel-furnace": "steel-furnace",
    "electric-furnace": "electric-furnace",
    "assembling-machine-1": "assembling-machine-1",
    "assembling-machine-2": "assembling-machine-2",
    "assembling-machine-3": "assembling-machine-3",
    "foundry": "foundry",
    "electromagnetic-plant": "electromagnetic-plant",
    "biochamber": "biochamber",
    "cryogenic-plant": "cryogenic-plant",
    "chemical-plant": "chemical-plant",
    "oil-refinery": "oil-refinery",
    "centrifuge": "centrifuge",
    "recycler": "recycler",
}


def _dominant_producer_recipe(decoded: dict[str, Any]
                              ) -> Optional[tuple[str, str, int]]:
    """Find the (machine, recipe, count) that drives the blueprint's output.

    Picks the (machine_type, recipe) pair with the highest entity count
    among assemblers / foundries / chemical-plants / refineries / etc.
    Furnaces don't carry an explicit recipe in the blueprint -- we treat
    them as a separate case below. Returns None if nothing matches.
    """
    counter: dict[tuple[str, str], int] = {}
    for e in _walk_entities(decoded):
        name = e.get("name", "")
        recipe = e.get("recipe")
        if not recipe:
            continue
        if name not in _MACHINE_DEFAULTS:
            continue
        key = (name, recipe)
        counter[key] = counter.get(key, 0) + 1
    if not counter:
        return None
    (machine, recipe), count = max(
        counter.items(), key=lambda kv: (kv[1], kv[0][1])
    )
    return (machine, recipe, count)


def _estimate_throughput(decoded: dict[str, Any]
                         ) -> Optional[ThroughputEstimate]:
    """Best-effort items/sec estimate for the dominant producer.

    Vanilla baseline: no modules, no beacons, no quality, no research.
    The user's actual layout may differ; we surface that in the notes.
    """
    if not _HAVE_RATES:
        return None

    pick = _dominant_producer_recipe(decoded)
    if pick is None:
        # Furnaces don't carry a recipe in the blueprint. If we have a
        # smelter array, guess "iron-plate" only when the blueprint icons
        # explicitly point at it; otherwise we punt.
        counts = _entity_counts(decoded)
        n_stone = counts.get("stone-furnace", 0)
        n_steel = counts.get("steel-furnace", 0)
        n_elec = counts.get("electric-furnace", 0)
        n_total = n_stone + n_steel + n_elec
        if n_total == 0:
            return None
        machine = ("electric-furnace" if n_elec >= max(n_stone, n_steel)
                   else "steel-furnace" if n_steel >= n_stone
                   else "stone-furnace")
        # No recipe info; bail with a "smelting (recipe unknown)" estimate.
        # We still produce a record so the user can confirm or correct.
        try:
            recipes = _rcalc.recipes_catalog()
        except Exception:
            return None
        # Pick iron-plate as a representative vanilla smelting recipe; the
        # user can correct via validation question.
        recipe = "iron-plate" if "iron-plate" in recipes else None
        if recipe is None:
            return None
        try:
            ro = compute_rates(RateInput(recipe=recipe, machine=machine,
                                         machine_count=n_total))
            ips = ro.outputs_per_second.get(recipe, 0.0)
            return ThroughputEstimate(
                primary_recipe=recipe,
                primary_machine=machine,
                items_per_second=ips,
                notes=(
                    f"smelter array assumption: {n_total} {machine}s smelting "
                    f"{recipe} (vanilla baseline, no modules); "
                    f"in-game recipe is set on the furnaces directly so this "
                    "could be steel-plate or copper-plate instead -- confirm."
                ),
            )
        except Exception:
            return None

    machine, recipe, n_machines = pick
    try:
        ro = compute_rates(RateInput(recipe=recipe, machine=machine,
                                     machine_count=n_machines))
        ips = ro.outputs_per_second.get(recipe, 0.0)
        return ThroughputEstimate(
            primary_recipe=recipe,
            primary_machine=machine,
            items_per_second=ips,
            notes=(
                f"vanilla baseline: {n_machines} {machine}(s), no modules / "
                "beacons / quality / research; in-game throughput will be "
                "higher if you have prod modules or beacons applied."
            ),
        )
    except Exception as exc:
        return ThroughputEstimate(
            primary_recipe=recipe,
            primary_machine=machine,
            items_per_second=0.0,
            notes=f"rate calc failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Validation questions
# ---------------------------------------------------------------------------

def _validation_questions(record: InventoryRecord, decoded: dict[str, Any]
                          ) -> list[str]:
    """Generate 2-4 concrete questions the user should answer."""
    qs: list[str] = []
    label = record.label or "(unnamed)"
    purpose = record.purpose_guess

    qs.append(f"Is this {label!r} actually used as a {purpose}? "
              "If not, what's its real purpose?")

    if record.throughput_estimate is not None:
        ips = record.throughput_estimate.items_per_second
        recipe = record.throughput_estimate.primary_recipe
        machine = record.throughput_estimate.primary_machine
        qs.append(
            f"Is the throughput target ~{ips:.2f} {recipe}/s "
            f"({machine}, vanilla baseline)? Different by how much?"
        )

    enabled_mods = record.mod_compat.get("enabled", [])
    disabled = record.mod_compat.get("disabled", [])
    missing = record.mod_compat.get("missing", [])
    if disabled:
        qs.append(
            f"This blueprint expects DISABLED mods {disabled}. "
            "Was it designed for those and you turned them off, or is the "
            "blueprint stale and should be deleted/updated?"
        )
    if missing:
        qs.append(
            f"This blueprint references mods you do NOT have installed: "
            f"{missing}. Do you remember where it came from / do you want "
            "the modern equivalent?"
        )
    if record.unknown_entities:
        legacy = [u for u in record.unknown_entities if u.status == "legacy_renamed"]
        unknown = [u for u in record.unknown_entities if u.status == "unknown_entity"]
        if legacy:
            mapping = ", ".join(f"{u.name} -> {u.suggested_name}" for u in legacy)
            qs.append(
                "This blueprint uses 1.x-era entity names "
                f"({mapping}). OK to leave as-is (game migrates them) or do "
                "you want the blueprint rewritten to the 2.0 names?"
            )
        if unknown:
            names = ", ".join(u.name for u in unknown)
            qs.append(
                f"Unknown entity names found ({names}). Do these come from "
                "a mod you uninstalled? Should the inventory drop them or "
                "wait for you to re-enable the mod?"
            )

    counts = _entity_counts(decoded)
    n_furnace = sum(v for n, v in counts.items() if n.endswith("-furnace") or n == "stone-furnace")
    if n_furnace >= 4:
        qs.append(
            f"Furnace count is {n_furnace} -- intentional? "
            "(12 saturates a yellow belt, 24 a red belt, 48 a blue belt.)"
        )

    if not enabled_mods and not disabled and not missing:
        qs.append("Is this a vanilla blueprint (base + DLC only)?")

    # Cap at 4 to keep the digest scannable.
    return qs[:4]


# ---------------------------------------------------------------------------
# Source enumerators
# ---------------------------------------------------------------------------

def _id_for(prefix: str, n: int) -> str:
    return f"{prefix}_{n:03d}"


def _from_dat(dat_path: pathlib.Path, start_index: int = 1
              ) -> list[InventoryRecord]:
    """Walk the binary blueprint-storage-2.dat file (envelope-only)."""
    if not dat_path.exists():
        return []
    try:
        header, entries = bsf.parse_storage_file(str(dat_path))
    except Exception as exc:
        rec = InventoryRecord(
            id=_id_for("user_dat", start_index),
            source=str(dat_path),
            label="(parse failed)",
            kind="envelope-only",
            string_size_bytes=0,
            decoded={},
            purpose_guess="binary storage parse failed",
            purpose_confidence="low",
            purpose_reasons=[f"parser error: {exc}"],
            mod_compat={"required_mods": [], "enabled": [], "disabled": [],
                        "missing": [], "zip_only": [],
                        "substitutes_available": [],
                        "policy": "n/a"},
            notes=[
                "Could not parse blueprint-storage-2.dat. The format is "
                "undocumented; we only support a subset. To populate this "
                "entry, export the blueprint string from inside the game "
                "and run `tools/blueprint_storage.py import-string`."
            ],
        )
        return [rec]

    out: list[InventoryRecord] = []
    used = sum(1 for e in entries if e.used)
    halt_reason: Optional[str] = None
    for e in entries:
        if not e.used:
            continue
        if e.parse_error and not e.label and e.kind != "blueprint":
            # The walk stops here (book bodies aren't decoded). Record
            # this as the "halt-on-book" sentinel for the digest.
            halt_reason = (
                f"binary walk halted at slot {e.index} "
                f"(kind={e.kind}, label={e.label!r}); body decoder not "
                "implemented for that kind"
            )
            n = start_index + len(out)
            out.append(InventoryRecord(
                id=_id_for("user_dat", n),
                source=f"{dat_path}#slot-{e.index}",
                label=e.label or "(no label)",
                kind="envelope-only",
                string_size_bytes=int(e.content_size or 0),
                decoded={
                    "envelope_only": True,
                    "binary_offset": hex(e.offset),
                    "in_game_kind": e.kind,
                },
                purpose_guess=f"{e.kind or 'unknown'} (envelope-only; body not decoded)",
                purpose_confidence="low",
                purpose_reasons=[
                    "the dat-file body parser does not yet handle this "
                    "kind; export from in-game to inventory contents",
                ],
                mod_compat={"required_mods": [], "enabled": [], "disabled": [],
                            "missing": [], "zip_only": [],
                            "substitutes_available": [],
                            "policy": "n/a (envelope-only)"},
                notes=[
                    f"Parsed envelope only. Header reports object_count="
                    f"{header.object_count}, "
                    f"walk reached slot {e.index} of that total.",
                    "To populate this entry, open the in-game blueprint "
                    "library, click this blueprint, choose 'Export to "
                    "string', then run `tools/blueprint_storage.py "
                    "import-string '<paste>'`.",
                ],
                validation_questions=[
                    f"Slot {e.index} in your in-game library has the label "
                    f"{(e.label or '(no label)')!r} and is a {e.kind}. Do "
                    "you want to export it manually so we can decode the "
                    "contents?",
                ],
            ))
            break

        n = start_index + len(out)
        # We have the envelope (kind, label, content_size, raw_content) but
        # the body bytes are NOT a blueprint string -- they're the engine's
        # internal format. We surface the metadata so the user sees it.
        rec = InventoryRecord(
            id=_id_for("user_dat", n),
            source=f"{dat_path}#slot-{e.index}",
            label=e.label or "(no label)",
            kind="envelope-only",
            string_size_bytes=int(e.content_size or 0),
            decoded={
                "envelope_only": True,
                "binary_offset": hex(e.offset),
                "in_game_kind": e.kind,
                "generation": e.generation,
                "item_name": e.item_name,
            },
            purpose_guess="envelope-only (body in in-game binary format)",
            purpose_confidence="low",
            purpose_reasons=[
                "blueprint-storage-2.dat body bytes are NOT a blueprint "
                "string; we only have label + size + kind",
            ],
            mod_compat={"required_mods": [], "enabled": [], "disabled": [],
                        "missing": [], "zip_only": [],
                        "substitutes_available": [],
                        "policy": "n/a (envelope-only)"},
            notes=[
                f"Header reports {header.object_count} total objects in the "
                f"file; we walked {used} entries.",
                "Body decoding is not yet implemented for the binary "
                ".dat format. Export this blueprint from inside Factorio "
                "via Library -> the blueprint -> 'Export to string', save "
                "into library/personal/, and re-run inventory to get full "
                "details.",
            ],
            validation_questions=[
                f"Slot {e.index}: label={e.label!r}, kind={e.kind}, "
                f"content_size={e.content_size}. Confirm you can find it "
                "in your in-game library?",
                "Do you want to manually export this blueprint so we can "
                "inventory its entities?",
            ],
        )
        out.append(rec)

    if halt_reason and out:
        out[-1].notes.append(halt_reason)

    return out


def _from_personal(root: pathlib.Path, start_index: int = 1
                   ) -> list[InventoryRecord]:
    """Walk library/personal/*.bp and library/personal/<book>/*.bp."""
    out: list[InventoryRecord] = []
    if not root.is_dir():
        return out
    n = start_index
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or child.name.startswith("_"):
            continue
        if child.is_file() and child.suffix == ".bp":
            rec = _record_from_bp_file(
                child, _id_for("user_lib", n), source_root=root)
            if rec is not None:
                out.append(rec)
                n += 1
        elif child.is_dir():
            book_meta = child / "_book.json"
            if book_meta.exists():
                for bp in sorted(child.glob("*.bp")):
                    rec = _record_from_bp_file(
                        bp, _id_for("user_lib", n), source_root=root,
                        book=child.name)
                    if rec is not None:
                        out.append(rec)
                        n += 1
    return out


def _from_external(root: pathlib.Path, start_index: int = 1
                   ) -> list[InventoryRecord]:
    """Walk library/external/<site>/*.bp."""
    out: list[InventoryRecord] = []
    if not root.is_dir():
        return out
    n = start_index
    for site_dir in sorted(root.iterdir()):
        if not site_dir.is_dir():
            continue
        for bp in sorted(site_dir.glob("*.bp")):
            rec = _record_from_bp_file(
                bp, _id_for("ext", n),
                source_root=root, site=site_dir.name,
            )
            if rec is not None:
                out.append(rec)
                n += 1
    return out


def _record_from_bp_file(path: pathlib.Path, rec_id: str,
                         source_root: pathlib.Path,
                         book: Optional[str] = None,
                         site: Optional[str] = None
                         ) -> Optional[InventoryRecord]:
    """Build an InventoryRecord from one .bp file path."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return InventoryRecord(
            id=rec_id, source=str(path),
            label=path.stem, kind="unparseable",
            string_size_bytes=0,
            decoded={},
            purpose_guess="(unreadable file)",
            purpose_confidence="low",
            purpose_reasons=[f"OS error: {exc}"],
            mod_compat={"required_mods": [], "enabled": [], "disabled": [],
                        "missing": [], "zip_only": [],
                        "substitutes_available": [], "policy": "n/a"},
            notes=[f"failed to read {path}"],
        )

    try:
        decoded = blueprint_codec.decode(raw)
    except Exception as exc:
        return InventoryRecord(
            id=rec_id, source=str(path),
            label=path.stem, kind="unparseable",
            string_size_bytes=len(raw),
            decoded={},
            purpose_guess="(undecodable blueprint string)",
            purpose_confidence="low",
            purpose_reasons=[f"decode error: {exc}"],
            mod_compat={"required_mods": [], "enabled": [], "disabled": [],
                        "missing": [], "zip_only": [],
                        "substitutes_available": [], "policy": "n/a"},
            notes=["The .bp file is not a valid blueprint string."],
        )

    label = _label_of(decoded) or path.stem
    kind = _kind_of(decoded)
    cls = classify(decoded)
    summary = _summarise_decoded(decoded)
    compat, unknowns = _mod_compat_for(decoded)
    throughput = _estimate_throughput(decoded)

    rel_source = str(path)
    try:
        rel_source = str(path.relative_to(source_root.parent))
    except ValueError:
        pass
    if book:
        rel_source = f"{rel_source} (book: {book})"
    if site:
        rel_source = f"{rel_source} (external: {site})"

    rec = InventoryRecord(
        id=rec_id,
        source=rel_source,
        label=label,
        kind=kind,
        string_size_bytes=len(raw),
        decoded=summary,
        purpose_guess=cls.label,
        purpose_confidence=cls.confidence,
        purpose_reasons=list(cls.reasons),
        mod_compat=compat,
        unknown_entities=unknowns,
        throughput_estimate=throughput,
    )
    rec.validation_questions = _validation_questions(rec, decoded)
    return rec


# ---------------------------------------------------------------------------
# Markdown digest
# ---------------------------------------------------------------------------

def _format_digest(records: list[InventoryRecord],
                   *, dat_count: int, lib_count: int, ext_count: int) -> str:
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append("# User blueprint inventory")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append(
        f"Sources scanned: blueprint-storage-2.dat ({dat_count} reachable), "
        f"library/personal/ ({lib_count}), library/external/ ({ext_count})"
    )
    lines.append("")

    # ---- Summary -----------------------------------------------------------
    total = len(records)
    decoded_records = [r for r in records if r.kind not in ("envelope-only", "unparseable")]
    n_decoded = len(decoded_records)
    n_envelope = sum(1 for r in records if r.kind == "envelope-only")
    n_unparse = sum(1 for r in records if r.kind == "unparseable")

    n_vanilla = sum(
        1 for r in decoded_records
        if not (set(r.mod_compat.get("required_mods", []))
                - {"base", "core", "space-age", "quality", "elevated-rails"})
    )
    n_space_age = sum(
        1 for r in decoded_records
        if "space-age" in r.mod_compat.get("required_mods", [])
    )
    n_other = sum(
        1 for r in decoded_records
        if (set(r.mod_compat.get("required_mods", []))
            - {"base", "core", "space-age", "quality", "elevated-rails"})
    )
    n_unknown = sum(1 for r in decoded_records if r.unknown_entities)

    lines.append("## Summary")
    lines.append(f"- Total blueprints: {total}")
    lines.append(f"- Fully decoded: {n_decoded} (envelope-only: {n_envelope}, unparseable: {n_unparse})")
    lines.append(f"- Vanilla / DLC only: {n_vanilla}")
    lines.append(f"- Space Age required: {n_space_age}")
    lines.append(f"- Other-mod required: {n_other}")
    lines.append(f"- Has unknown / legacy entities: {n_unknown}")
    lines.append("")

    # ---- By mod requirement -----------------------------------------------
    lines.append("## By mod requirement")
    by_mod: dict[str, int] = {}
    for r in decoded_records:
        req = tuple(sorted(r.mod_compat.get("required_mods", []) or ["(none)"]))
        key = " + ".join(req) if req else "(none)"
        by_mod[key] = by_mod.get(key, 0) + 1
    for k, v in sorted(by_mod.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {k}: {v}")
    lines.append("")

    # ---- Per-blueprint detail --------------------------------------------
    lines.append("## Per-blueprint detail")
    lines.append("")
    for r in records:
        lines.append(f"### {r.id} -- {r.label} ({r.purpose_guess})")
        lines.append(f"- source: `{r.source}`")
        lines.append(f"- kind: {r.kind}; size: {r.string_size_bytes:,} bytes")
        if r.decoded.get("entity_count") is not None:
            bbox = r.decoded.get("bbox") or {}
            ec = r.decoded.get("entity_count")
            lines.append(
                f"- {ec} entities, {bbox.get('width','?')}x{bbox.get('height','?')}"
            )
        top = r.decoded.get("top_entities") or []
        if top:
            top_str = ", ".join(f"{n} x{c}" for n, c in top[:5])
            lines.append(f"- top entities: {top_str}")
        rm = r.mod_compat.get("required_mods") or []
        if rm:
            lines.append(f"- required mods: {', '.join(rm)}")
        if r.mod_compat.get("disabled"):
            lines.append(f"- DISABLED in your install: {', '.join(r.mod_compat['disabled'])}")
        if r.mod_compat.get("missing"):
            lines.append(f"- NOT INSTALLED: {', '.join(r.mod_compat['missing'])}")
        for u in r.unknown_entities:
            if u.status == "legacy_renamed":
                lines.append(f"- LEGACY rename: `{u.name}` x{u.count} -> `{u.suggested_name}` (game auto-migrates)")
            else:
                lines.append(f"- UNKNOWN entity: `{u.name}` x{u.count} (no source mod found)")
        if r.throughput_estimate:
            te = r.throughput_estimate
            lines.append(
                f"- throughput estimate: ~{te.items_per_second:.2f} {te.primary_recipe}/s "
                f"({te.primary_machine}, vanilla baseline)"
            )
        if r.purpose_reasons:
            lines.append(f"- classifier reasons: {'; '.join(r.purpose_reasons)}")
        for note in r.notes:
            lines.append(f"- NOTE: {note}")
        if r.validation_questions:
            lines.append("- VALIDATE:")
            for q in r.validation_questions:
                lines.append(f"  - {q}")
        lines.append("")

    # ---- Aggregated open questions ----------------------------------------
    lines.append("## Open questions for the user")
    lines.append("")
    qn = 1
    for r in records:
        for q in r.validation_questions:
            lines.append(f"{qn}. ({r.id}) {q}")
            qn += 1
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main / CLI
# ---------------------------------------------------------------------------

def build_inventory(
    *,
    dat_path: Optional[pathlib.Path] = None,
    personal_root: pathlib.Path = DEFAULT_PERSONAL,
    external_root: Optional[pathlib.Path] = None,
    limit: Optional[int] = None,
) -> tuple[list[InventoryRecord], dict[str, int]]:
    """Build an inventory; returns (records, source_counts)."""
    records: list[InventoryRecord] = []
    counts: dict[str, int] = {"dat": 0, "personal": 0, "external": 0}

    if dat_path is not None:
        dat_records = _from_dat(dat_path, start_index=1)
        records.extend(dat_records)
        counts["dat"] = len(dat_records)

    lib_records = _from_personal(personal_root, start_index=len(records) + 1)
    records.extend(lib_records)
    counts["personal"] = len(lib_records)

    if external_root is not None:
        ext_records = _from_external(external_root, start_index=len(records) + 1)
        records.extend(ext_records)
        counts["external"] = len(ext_records)

    if limit is not None and limit > 0:
        records = records[:limit]
    return records, counts


def write_outputs(records: list[InventoryRecord],
                  counts: dict[str, int],
                  manifest_path: pathlib.Path,
                  digest_path: pathlib.Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_counts": counts,
        "records": [r.to_dict() for r in records],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(
        _format_digest(
            records,
            dat_count=counts.get("dat", 0),
            lib_count=counts.get("personal", 0),
            ext_count=counts.get("external", 0),
        ),
        encoding="utf-8",
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="inventory_user_blueprints",
        description="Inventory the user's Factorio blueprint library.",
    )
    p.add_argument("--out", default=str(DEFAULT_DIGEST),
                   help=f"path to the markdown digest (default: {DEFAULT_DIGEST})")
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST),
                   help=f"path to the JSON manifest (default: {DEFAULT_MANIFEST})")
    p.add_argument("--include-external", action="store_true",
                   help="also walk library/external/<site>/*.bp")
    p.add_argument("--limit", type=int, default=None,
                   help="cap the number of records (debugging)")
    p.add_argument("--dat", default=str(DEFAULT_DAT),
                   help=f"path to blueprint-storage-2.dat (default: {DEFAULT_DAT})")
    p.add_argument("--no-dat", action="store_true",
                   help="skip the binary .dat file (handy in tests)")
    p.add_argument("--personal", default=str(DEFAULT_PERSONAL),
                   help=f"path to personal library root (default: {DEFAULT_PERSONAL})")
    p.add_argument("--external", default=str(DEFAULT_EXTERNAL),
                   help=f"path to external library root (default: {DEFAULT_EXTERNAL})")
    args = p.parse_args(argv)

    dat_path: Optional[pathlib.Path]
    if args.no_dat:
        dat_path = None
    else:
        dat_path = pathlib.Path(args.dat)
    external_root: Optional[pathlib.Path] = (
        pathlib.Path(args.external) if args.include_external else None
    )

    records, counts = build_inventory(
        dat_path=dat_path,
        personal_root=pathlib.Path(args.personal),
        external_root=external_root,
        limit=args.limit,
    )
    manifest_path = pathlib.Path(args.manifest)
    digest_path = pathlib.Path(args.out)
    write_outputs(records, counts, manifest_path, digest_path)
    print(f"wrote {manifest_path} ({len(records)} records)")
    print(f"wrote {digest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
