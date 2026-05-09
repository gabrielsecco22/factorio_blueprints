#!/usr/bin/env python3
"""Decode + render a Factorio blueprint string into an ASCII grid.

Stdlib only. Reuses ``tools/blueprint_codec.py`` for decoding and
``harness/catalog.py`` for entity footprints + mod ownership.

CLI
---

    render_blueprint.py <string-or-file>             ASCII grid + JSON summary
    render_blueprint.py --json <string-or-file>      structural summary only
    render_blueprint.py --grid-only <string-or-file> ASCII grid only
    render_blueprint.py --max-width 200 <string>     truncate huge blueprints
    render_blueprint.py --bbox 0,0,80,40 <string>    render a rectangular window

If the argument is the path of an existing file, its contents are read
as the blueprint string (handy for long strings). Otherwise the argument
is treated as the blueprint string itself.

Symbol table (matches ``.claude/agents/blueprint-visual-validator.md``)
----------------------------------------------------------------------

    F  stone/steel furnace                 A  assembling-machine
    E  electromagnetic-plant               Y  foundry
    K  chemical-plant                      O  oil-refinery
    R  recycler                            B  boiler / burner-mining-drill
    M  electric-mining-drill / big-mining-drill
    C  container/chest (any wooden/iron/steel/logistic chest)
    S  solar-panel (any tier)              Q  accumulator (any tier)
    +  small/medium/big electric pole      #  substation
    L  lab / biolab
    H  beacon
    G  agricultural-tower / biochamber
    T  turret (any)                        N  nuclear-reactor / heat-exchanger / heat-pipe
    =  pipe (horizontal hint)              |  pipe (vertical hint) / pipe-to-ground
    >  belt facing east                    <  belt facing west
    ^  belt facing north                   v  belt facing south
    i  inserter facing N                   u  inserter facing S
    {  inserter facing E                   }  inserter facing W
    .  empty tile (renderer collapses dense rows; not stored)
    '  continuation tile of a multi-tile entity
    ?  unknown entity / non-cardinal direction (per-entity warning emitted)

For inserters / belts, the symbol case may vary by tier in the agent's
prose; the renderer always emits the lowercase glyph and lets the agent
disambiguate by reading entity_counts.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any, Iterable, Optional

# Make sibling modules importable regardless of cwd.
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import blueprint_codec  # noqa: E402

# ``harness.catalog`` may not be importable if the user shipped a slim
# install; we fall back to a static footprint table so the renderer
# always works.
try:
    from harness import catalog as _catalog  # noqa: E402
    _HAVE_CATALOG = True
except Exception:  # pragma: no cover - defensive
    _catalog = None
    _HAVE_CATALOG = False


# ---------------------------------------------------------------------------
# Symbol resolution
# ---------------------------------------------------------------------------

# Direct entity-name -> symbol overrides.
_NAME_SYMBOLS: dict[str, str] = {
    "substation": "#",
    "solar-panel": "S",
    "accumulator": "Q",
    "small-electric-pole": "+",
    "medium-electric-pole": "+",
    "big-electric-pole": "+",
    "beacon": "H",
    "lab": "L",
    "biolab": "L",
    "biochamber": "G",
    "agricultural-tower": "G",
    "captive-biter-spawner": "G",
    "electromagnetic-plant": "E",
    "foundry": "Y",
    "chemical-plant": "K",
    "oil-refinery": "O",
    "recycler": "R",
    "boiler": "B",
    "burner-mining-drill": "B",
    "electric-mining-drill": "M",
    "big-mining-drill": "M",
    "nuclear-reactor": "N",
    "heat-exchanger": "N",
    "heat-pipe": "N",
    "steam-engine": "N",
    "steam-turbine": "N",
    "pipe": "=",
    "pipe-to-ground": "|",
    "storage-tank": "=",
    "wooden-chest": "C",
    "iron-chest": "C",
    "steel-chest": "C",
    "active-provider-chest": "C",
    "passive-provider-chest": "C",
    "storage-chest": "C",
    "buffer-chest": "C",
    "requester-chest": "C",
    "logistic-chest-active-provider": "C",
    "logistic-chest-passive-provider": "C",
    "logistic-chest-storage": "C",
    "logistic-chest-buffer": "C",
    "logistic-chest-requester": "C",
}

# Substring rules for whole families. Order matters: first match wins.
_SUFFIX_RULES: list[tuple[str, str]] = [
    ("stone-furnace", "F"),
    ("steel-furnace", "F"),
    ("electric-furnace", "F"),
    ("furnace", "F"),
    ("assembling-machine", "A"),
    ("assembler", "A"),
    ("electromagnetic-plant", "E"),
    ("foundry", "Y"),
    ("chemical-plant", "K"),
    ("oil-refinery", "O"),
    ("recycler", "R"),
    ("turret", "T"),
    ("artillery", "T"),
    ("flamethrower-turret", "T"),
    ("rocket-silo", "X"),
    ("crusher", "K"),
    ("centrifuge", "Y"),
    ("mining-drill", "M"),
    ("loader", ">"),
    ("transport-belt", None),  # handled by direction
    ("underground-belt", None),
    ("splitter", None),
    ("inserter", None),  # handled by direction + variant
    ("electric-pole", "+"),
    ("solar", "S"),
    ("accumulator", "Q"),
    ("chest", "C"),
    ("tank", "="),
    ("pipe", "="),
]

# Inserter symbols indexed by direction.
_INSERTER_DIR_SYMBOLS = {
    0: "i",   # N
    4: "{",   # E (drops east, pickup west; arrow-style not enforced)
    8: "u",   # S
    12: "}",  # W
}

# Belt symbols by direction.
_BELT_DIR_SYMBOLS = {
    0: "^",   # N
    4: ">",   # E
    8: "v",   # S
    12: "<",  # W
}


def symbol_for(name: str, direction: int) -> tuple[str, list[str]]:
    """Resolve an ASCII symbol for an entity.

    Returns ``(symbol, warnings)``. ``symbol`` is a single character.
    ``warnings`` lists per-entity issues (unknown entity, non-cardinal
    direction, etc.).
    """
    warnings: list[str] = []

    # Direction-bearing families first.
    if "transport-belt" in name or name.endswith("-belt") and "underground" not in name:
        sym = _BELT_DIR_SYMBOLS.get(direction)
        if sym is None:
            warnings.append(f"non-cardinal direction {direction} on belt {name}")
            return ("?", warnings)
        return (sym, warnings)
    if "underground-belt" in name:
        sym = _BELT_DIR_SYMBOLS.get(direction, "?")
        if sym == "?":
            warnings.append(f"non-cardinal direction {direction} on underground-belt {name}")
        # Distinguish underground belts visually; capitalise.
        return (sym.upper() if sym != "?" else "?", warnings)
    if "splitter" in name:
        # Splitters have a width of 2 in the cross-axis. Render as the
        # belt arrow uppercased (renderer also fills the second tile via
        # the multi-tile path).
        sym = _BELT_DIR_SYMBOLS.get(direction, "?")
        if sym == "?":
            warnings.append(f"non-cardinal direction {direction} on splitter {name}")
        return (sym, warnings)
    if "inserter" in name:
        sym = _INSERTER_DIR_SYMBOLS.get(direction)
        if sym is None:
            warnings.append(f"non-cardinal direction {direction} on inserter {name}")
            return ("?", warnings)
        # Visually mark variants by uppercasing.
        if any(p in name for p in ("fast-", "bulk-", "stack-", "filter-", "long-handed-")):
            sym = sym.upper()
        return (sym, warnings)

    if name in _NAME_SYMBOLS:
        return (_NAME_SYMBOLS[name], warnings)

    for needle, sym in _SUFFIX_RULES:
        if sym is None:
            continue
        if needle in name:
            return (sym, warnings)

    warnings.append(f"unknown entity {name!r}; rendering as '?'")
    return ("?", warnings)


# ---------------------------------------------------------------------------
# Footprint resolution
# ---------------------------------------------------------------------------

# Static fallback for when ``harness.catalog`` is unavailable.
_STATIC_FOOTPRINTS: dict[str, tuple[int, int]] = {
    "small-electric-pole": (1, 1),
    "medium-electric-pole": (1, 1),
    "big-electric-pole": (2, 2),
    "substation": (2, 2),
    "solar-panel": (3, 3),
    "accumulator": (2, 2),
    "transport-belt": (1, 1),
    "fast-transport-belt": (1, 1),
    "express-transport-belt": (1, 1),
    "turbo-transport-belt": (1, 1),
    "inserter": (1, 1),
    "fast-inserter": (1, 1),
    "long-handed-inserter": (1, 1),
    "burner-inserter": (1, 1),
    "bulk-inserter": (1, 1),
    "stack-inserter": (1, 1),
    "stone-furnace": (2, 2),
    "steel-furnace": (2, 2),
    "electric-furnace": (3, 3),
    "assembling-machine-1": (3, 3),
    "assembling-machine-2": (3, 3),
    "assembling-machine-3": (3, 3),
    "beacon": (3, 3),
    "lab": (3, 3),
    "boiler": (3, 2),
    "steam-engine": (3, 5),
    "pipe": (1, 1),
    "pipe-to-ground": (1, 1),
}


def resolve_footprint(name: str, warnings: list[str]) -> tuple[int, int]:
    if _HAVE_CATALOG:
        try:
            return _catalog.footprint(name)
        except KeyError:
            pass
    if name in _STATIC_FOOTPRINTS:
        return _STATIC_FOOTPRINTS[name]
    warnings.append(f"footprint unknown for {name!r}; treating as 1x1")
    return (1, 1)


# ---------------------------------------------------------------------------
# Mod awareness
# ---------------------------------------------------------------------------


def _load_items_index() -> dict[str, str]:
    """Map entity (place_result) -> owning mod name. Empty if specs missing."""
    p = ROOT / "specs" / "items.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except Exception:
        return {}
    out: dict[str, str] = {}
    for it in data:
        pr = it.get("place_result")
        if pr:
            out[pr] = it.get("from_mod", "base") or "base"
    return out


def _load_user_mod_list() -> Optional[set[str]]:
    """Return the set of enabled mods in ``~/.factorio/mods/mod-list.json``.

    Returns None if the file is unreadable. Used to flag entities from
    disabled / missing mods.
    """
    p = pathlib.Path.home() / ".factorio" / "mods" / "mod-list.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except Exception:
        return None
    return {m["name"] for m in data.get("mods", []) if m.get("enabled")}


# ---------------------------------------------------------------------------
# Decoding helpers
# ---------------------------------------------------------------------------


def _read_input(arg: str) -> str:
    """Treat arg as a file path if it exists, else return it verbatim."""
    p = pathlib.Path(arg)
    if p.exists() and p.is_file():
        return p.read_text().strip()
    return arg.strip()


def _entity_nw_tile(name: str, position: dict[str, float], footprint: tuple[int, int]) -> tuple[int, int]:
    """Inverse of ``layout.PlacedEntity.position``.

    position = NW + (w-1)/2 along each axis. So NW = position - (w-1)/2.
    Round to int because positions are stored as floats in JSON but the
    underlying tile grid is integer.
    """
    w, h = footprint
    nx = position["x"] - (w - 1) / 2.0
    ny = position["y"] - (h - 1) / 2.0
    return (int(round(nx)), int(round(ny)))


# ---------------------------------------------------------------------------
# Public render API
# ---------------------------------------------------------------------------


MAX_RENDER_TILES = 1000  # per-axis hard cap


def render(
    blueprint: dict[str, Any],
    *,
    bbox: Optional[tuple[int, int, int, int]] = None,
    max_width: Optional[int] = None,
) -> dict[str, Any]:
    """Render a decoded blueprint object.

    Returns a dict with keys:
        ``grid``      -- list[str], each row pre-joined
        ``summary``   -- structural summary dict (see module docstring)

    ``bbox`` (x_min, y_min, x_max, y_max) clips the render to a window.
    ``max_width`` truncates rendered rows to that many characters with a
    trailing "..." marker. The summary always reflects the FULL blueprint;
    only the ASCII grid honours the window.
    """
    bp = blueprint.get("blueprint")
    if bp is None:
        # Some exports wrap with blueprint-book; we don't support those.
        if "blueprint_book" in blueprint:
            raise ValueError(
                "blueprint-book not supported by render_blueprint; "
                "extract a single blueprint first"
            )
        raise ValueError("decoded object has no 'blueprint' key")
    entities = bp.get("entities") or []
    tiles = bp.get("tiles") or []

    items_to_mod = _load_items_index()
    user_mods = _load_user_mod_list()

    warnings: list[str] = []
    placed: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    mods_referenced: set[str] = set()

    # First pass: resolve footprints, NW tiles, symbols, and counts. Also
    # compute the "full" bbox over all entities.
    full_min_x: Optional[int] = None
    full_min_y: Optional[int] = None
    full_max_x: Optional[int] = None
    full_max_y: Optional[int] = None
    for ent in entities:
        name = ent.get("name", "")
        pos = ent.get("position") or {}
        if "x" not in pos or "y" not in pos:
            warnings.append(f"entity {ent.get('entity_number')!r} has no position; skipped")
            continue
        direction = int(ent.get("direction", 0))
        fp = resolve_footprint(name, warnings)
        nw = _entity_nw_tile(name, pos, fp)
        sym, ent_warns = symbol_for(name, direction)
        warnings.extend(ent_warns)
        counts[name] = counts.get(name, 0) + 1
        mod = items_to_mod.get(name, "base" if not items_to_mod else "unknown")
        mods_referenced.add(mod)

        x, y = nw
        w, h = fp
        full_min_x = x if full_min_x is None else min(full_min_x, x)
        full_min_y = y if full_min_y is None else min(full_min_y, y)
        full_max_x = (x + w - 1) if full_max_x is None else max(full_max_x, x + w - 1)
        full_max_y = (y + h - 1) if full_max_y is None else max(full_max_y, y + h - 1)

        placed.append({
            "name": name,
            "direction": direction,
            "nw": nw,
            "fp": fp,
            "symbol": sym,
        })

    # Tiles (floor tiles like "stone-path"). We don't draw them but we
    # do count and report them.
    tile_counts: dict[str, int] = {}
    for t in tiles:
        n = t.get("name")
        if n:
            tile_counts[n] = tile_counts.get(n, 0) + 1

    if full_min_x is None:
        # Empty blueprint.
        return {
            "grid": [],
            "summary": {
                "bbox": {"x_min": 0, "x_max": 0, "y_min": 0, "y_max": 0, "width": 0, "height": 0},
                "entity_counts": {},
                "by_category": {},
                "fluid_systems": [],
                "circuit_networks": [],
                "tiles": tile_counts,
                "mods_referenced": [],
                "mods_missing_in_user_install": [],
                "warnings": warnings,
            },
        }

    full_bbox = {
        "x_min": full_min_x,
        "y_min": full_min_y,
        "x_max": full_max_x,
        "y_max": full_max_y,
        "width": full_max_x - full_min_x + 1,
        "height": full_max_y - full_min_y + 1,
    }

    # Determine render window.
    if bbox is not None:
        rx_min, ry_min, rx_max, ry_max = bbox
    else:
        rx_min, ry_min, rx_max, ry_max = full_min_x, full_min_y, full_max_x, full_max_y

    rw = rx_max - rx_min + 1
    rh = ry_max - ry_min + 1
    if rw <= 0 or rh <= 0:
        raise ValueError(f"bbox produced empty render window: {rw}x{rh}")
    if rw > MAX_RENDER_TILES or rh > MAX_RENDER_TILES:
        raise ValueError(
            f"render window {rw}x{rh} exceeds MAX_RENDER_TILES={MAX_RENDER_TILES}; "
            "pass --bbox to render a sub-window"
        )

    # Build the 2D char grid filled with '.'.
    grid: list[list[str]] = [["."] * rw for _ in range(rh)]

    for p in placed:
        x, y = p["nw"]
        w, h = p["fp"]
        sym = p["symbol"]
        for dy in range(h):
            for dx in range(w):
                gx = x + dx - rx_min
                gy = y + dy - ry_min
                if 0 <= gx < rw and 0 <= gy < rh:
                    if dx == 0 and dy == 0:
                        grid[gy][gx] = sym
                    else:
                        # Continuation tile -- only overwrite if empty so
                        # we don't mask a neighbour's primary symbol.
                        if grid[gy][gx] == ".":
                            grid[gy][gx] = "'"

    rows = ["".join(row) for row in grid]
    if max_width is not None and max_width > 0:
        rows = [(r[: max_width - 3] + "...") if len(r) > max_width else r for r in rows]

    # By-category aggregation (best-effort; uses substrings).
    by_category = _categorise_counts(counts)

    # Fluid systems / circuit networks: cheap structural summary.
    fluid_systems = _summarise_fluid(entities)
    circuit_networks = _summarise_circuits(entities)

    # Mod awareness.
    missing_mods: list[str] = []
    if user_mods is not None:
        for m in mods_referenced:
            if m == "base":
                continue
            if m == "unknown":
                continue
            if m not in user_mods:
                missing_mods.append(m)

    summary = {
        "bbox": full_bbox,
        "render_window": {
            "x_min": rx_min,
            "y_min": ry_min,
            "x_max": rx_max,
            "y_max": ry_max,
            "width": rw,
            "height": rh,
        },
        "entity_counts": dict(sorted(counts.items())),
        "by_category": by_category,
        "fluid_systems": fluid_systems,
        "circuit_networks": circuit_networks,
        "tiles": tile_counts,
        "mods_referenced": sorted(mods_referenced),
        "mods_missing_in_user_install": sorted(missing_mods),
        "warnings": warnings,
    }
    return {"grid": rows, "summary": summary}


def _categorise_counts(counts: dict[str, int]) -> dict[str, int]:
    cats: dict[str, int] = {}
    def bump(cat: str, n: int) -> None:
        cats[cat] = cats.get(cat, 0) + n
    for name, n in counts.items():
        if "transport-belt" in name or "underground-belt" in name or "splitter" in name or "inserter" in name or "loader" in name:
            bump("logistics", n)
        elif "furnace" in name or "assembling-machine" in name or "foundry" in name or "chemical-plant" in name or "oil-refinery" in name or "recycler" in name or "electromagnetic-plant" in name or "biochamber" in name or "centrifuge" in name or "crusher" in name:
            bump("crafting", n)
        elif "mining-drill" in name:
            bump("extraction", n)
        elif "electric-pole" in name or name == "substation":
            bump("power_distribution", n)
        elif "solar-panel" in name or "accumulator" in name or "steam-engine" in name or "steam-turbine" in name or "boiler" in name or "nuclear-reactor" in name or "heat-exchanger" in name or "heat-pipe" in name:
            bump("power_generation", n)
        elif "pipe" in name or "tank" in name or "pump" in name:
            bump("fluid", n)
        elif "chest" in name or "container" in name or "warehouse" in name:
            bump("storage", n)
        elif "beacon" in name:
            bump("module_distribution", n)
        elif "turret" in name or "wall" in name or "gate" in name:
            bump("defense", n)
        else:
            bump("other", n)
    return dict(sorted(cats.items()))


def _summarise_fluid(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Light fluid summary: count pipes/tanks; we don't trace networks."""
    pipes = sum(1 for e in entities if "pipe" in e.get("name", ""))
    tanks = sum(1 for e in entities if "tank" in e.get("name", ""))
    pumps = sum(1 for e in entities if "pump" in e.get("name", ""))
    if pipes == tanks == pumps == 0:
        return []
    return [{"pipes": pipes, "tanks": tanks, "pumps": pumps}]


def _summarise_circuits(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Count entities with circuit_connections / control_behavior."""
    wired = 0
    controlled = 0
    for e in entities:
        if e.get("connections") or e.get("circuit_connections"):
            wired += 1
        if e.get("control_behavior"):
            controlled += 1
    if wired == controlled == 0:
        return []
    return [{"wired_entities": wired, "controlled_entities": controlled}]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_bbox(s: str) -> tuple[int, int, int, int]:
    parts = s.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"--bbox expects 4 ints x_min,y_min,x_max,y_max; got {s!r}")
    try:
        a, b, c, d = (int(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--bbox values must be ints: {exc}")
    if c < a or d < b:
        raise argparse.ArgumentTypeError(f"--bbox max < min: {s!r}")
    return (a, b, c, d)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="render_blueprint",
        description="Render a Factorio blueprint string as ASCII + structural JSON.",
    )
    p.add_argument("input", help="blueprint string OR path to a file containing one")
    p.add_argument("--json", action="store_true", help="emit only the JSON summary")
    p.add_argument("--grid-only", action="store_true", help="emit only the ASCII grid")
    p.add_argument("--max-width", type=int, default=None, help="truncate rendered rows")
    p.add_argument("--bbox", type=_parse_bbox, default=None, help="render window x_min,y_min,x_max,y_max")

    args = p.parse_args(argv)

    if args.json and args.grid_only:
        p.error("--json and --grid-only are mutually exclusive")

    raw = _read_input(args.input)
    obj = blueprint_codec.decode(raw)
    out = render(obj, bbox=args.bbox, max_width=args.max_width)

    if args.json:
        json.dump(out["summary"], sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    # Grid first (with row coordinates on the left for orientation).
    grid = out["grid"]
    summary = out["summary"]
    win = summary.get("render_window") or summary["bbox"]
    y0 = win["y_min"]
    if grid:
        # Column header.
        x0 = win["x_min"]
        width = win["width"]
        # Print a short col ruler every 10 tiles.
        col_label = ""
        for i in range(width):
            if (x0 + i) % 10 == 0:
                col_label += str(((x0 + i) // 10) % 10)
            else:
                col_label += " "
        sys.stdout.write("     " + col_label + "\n")
        for i, row in enumerate(grid):
            sys.stdout.write(f"{y0 + i:>4} {row}\n")

    if args.grid_only:
        return 0

    sys.stdout.write("\n")
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
