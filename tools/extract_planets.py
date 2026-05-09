#!/usr/bin/env python3
"""
extract_planets.py - extract planet, quality, beacon, and surface-condition
specs from the live Factorio prototype dump.

Reads:
    specs/data-raw-dump.json   (~28 MB; produced by tools/dump_prototypes.sh)

Writes (under specs/):
    planets.json                       - 5 planets + space platform surface
    quality.json                       - quality tiers (excludes quality-unknown)
    beacons.json                       - every beacon prototype
    recipe_planet_restrictions.json    - recipes gated by surface_conditions
    entity_planet_restrictions.json    - entities gated by surface_conditions

Stdlib only. Python 3.10+.

CLI:
    python3 tools/extract_planets.py            # write all five files
    python3 tools/extract_planets.py --human    # also print a summary
    python3 tools/extract_planets.py --dump PATH  # override dump location
    python3 tools/extract_planets.py --out DIR    # override output dir
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DUMP = REPO_ROOT / "specs" / "data-raw-dump.json"
DEFAULT_OUT = REPO_ROOT / "specs"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENERGY_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([kMGTP]?)([WJ])\s*$")
_ENERGY_PREFIX = {"": 1.0, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15}


def parse_energy_to_kw(value: str | int | float | None) -> float | None:
    """Parse '480kW' / '10MW' / '400J' to kilowatts (or kJ for energy).

    Returns None if value is missing or unparseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1e3  # assume bare watts
    m = _ENERGY_RE.match(str(value))
    if not m:
        return None
    mag = float(m.group(1))
    pref = _ENERGY_PREFIX.get(m.group(2), 1.0)
    return (mag * pref) / 1e3  # always report in kilo-units


def detect_mod_from_paths(prototype: dict[str, Any]) -> str:
    """Heuristically determine the mod that owns a prototype by scanning
    asset path strings (e.g. '__space-age__/...'). Returns 'base' if
    nothing more specific is found.
    """
    seen: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, str):
            if o.startswith("__") and "__/" in o:
                seen.add(o.split("/")[0].strip("_"))
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(prototype)
    # Prefer the most specific non-core mod
    preference = [
        "space-age", "quality", "elevated-rails",
        "beacon-interface", "AdjustableModule", "Li-Module-Fix",
        "quality-seeds", "Wagon-quality-size", "accumulator-mk2",
        "promethium-belts", "YAPR", "visible-planets",
    ]
    for m in preference:
        if m in seen:
            return m
    for m in sorted(seen):
        if m not in ("base", "core"):
            return m
    if "base" in seen:
        return "base"
    return "base"


def detect_mod_from_name(name: str, default: str = "base") -> str:
    """Name-prefix heuristic for modded prototypes."""
    if name.startswith("beacon-interface--"):
        return "beacon-interface"
    return default


# ---------------------------------------------------------------------------
# Planets
# ---------------------------------------------------------------------------

def _surface_property_defaults(dump: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, p in dump.get("surface-property", {}).items():
        if "default_value" in p:
            out[name] = p["default_value"]
    return out


# Static curated lists. The autoplace_settings.entity dict on a planet
# contains hundreds of decoratives; we want the few entries that are
# actual hostiles or harvestables. These lists are derived from inspection
# of `data.raw.unit`, `data.raw.unit-spawner`, `data.raw.segmented-unit`,
# and `data.raw.spider-unit` in the dump.
_NATIVE_HOSTILES = {
    "nauvis": [
        "biter-spawner", "spitter-spawner",
        "small-biter", "medium-biter", "big-biter", "behemoth-biter",
        "small-spitter", "medium-spitter", "big-spitter", "behemoth-spitter",
        "small-worm-turret", "medium-worm-turret", "big-worm-turret",
        "behemoth-worm-turret",
    ],
    "vulcanus": ["small-demolisher", "medium-demolisher", "big-demolisher"],
    "fulgora": [],  # lightning is the hazard, not a creature
    "gleba": [
        "gleba-spawner", "gleba-spawner-small",
        "small-strafer-pentapod", "medium-strafer-pentapod", "big-strafer-pentapod",
        "small-stomper-pentapod", "medium-stomper-pentapod", "big-stomper-pentapod",
        "small-wriggler-pentapod", "medium-wriggler-pentapod", "big-wriggler-pentapod",
    ],
    "aquilo": [],
}

_PLANET_SOURCE_MOD = {
    "nauvis": "base",
    "vulcanus": "space-age",
    "fulgora": "space-age",
    "gleba": "space-age",
    "aquilo": "space-age",
}


def _planet_surface_props(planet: dict[str, Any], defaults: dict[str, float]) -> dict[str, float]:
    """Merge a planet's declared surface_properties with surface-property
    prototype defaults so every planet reports the full set."""
    sp = dict(defaults)
    sp.update(planet.get("surface_properties", {}))
    return sp


def _planet_resources(planet: dict[str, Any], all_resources: set[str]) -> list[str]:
    ents = (planet.get("map_gen_settings", {})
                  .get("autoplace_settings", {})
                  .get("entity", {})
                  .get("settings", {}))
    return sorted(set(ents.keys()) & all_resources)


def _trip_time_seconds(distance_units: int, ticks_per_second: int = 60) -> int | None:
    """Rough lower bound: with a max-speed thruster at ~3 km/s (3 tiles/tick
    in space-platform terms, per the Factorio devblog), the minimum trip
    time for a connection of length N is N / 180 seconds. This is a
    [VERIFY] approximation; actual time depends on platform mass and fuel.
    """
    if distance_units is None:
        return None
    # 180 tiles/sec is the documented max thruster speed cap in 2.0.
    return round(distance_units / 180)


def build_planets(dump: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    defaults = _surface_property_defaults(dump)
    all_resources = set(dump.get("resource", {}).keys())
    space_connections = dump.get("space-connection", {})

    # Index nauvis-X distances
    nauvis_distances: dict[str, int] = {}
    for sc in space_connections.values():
        a, b = sc.get("from"), sc.get("to")
        ln = sc.get("length")
        if a == "nauvis" and b and ln is not None:
            nauvis_distances[b] = ln
        elif b == "nauvis" and a and ln is not None:
            nauvis_distances[a] = ln

    for name, p in dump.get("planet", {}).items():
        sp = _planet_surface_props(p, defaults)
        resources = _planet_resources(p, all_resources)
        hostiles = _NATIVE_HOSTILES.get(name, [])
        # Compute "lacks" relative to nauvis as a rough delta
        nauvis_resources = set(_planet_resources(
            dump["planet"]["nauvis"], all_resources)) if "nauvis" in dump.get("planet", {}) else set()
        lacks = sorted(nauvis_resources - set(resources)) if name != "nauvis" else []

        dist = nauvis_distances.get(name)
        out.append({
            "name": name,
            "type": "planet",
            "starmap_distance": p.get("distance"),
            "starmap_orientation": p.get("orientation"),
            "starmap_magnitude": p.get("magnitude"),
            "gravity_pull": p.get("gravity_pull"),
            "solar_power_in_space": p.get("solar_power_in_space"),
            "surface_properties": sp,
            "starmap_distance_to_nauvis": dist,
            "trip_time_to_nauvis_seconds": _trip_time_seconds(dist) if dist else None,
            "native_resources": resources,
            "native_entities": hostiles,
            "lacks": lacks,
            "from_mod": _PLANET_SOURCE_MOD.get(name, detect_mod_from_paths(p)),
        })

    # Space platform pseudo-surface
    sp_surface = dump.get("surface", {}).get("space-platform")
    if sp_surface:
        out.append({
            "name": "space-platform",
            "type": "surface",
            "starmap_distance": None,
            "starmap_orientation": None,
            "starmap_magnitude": None,
            "gravity_pull": 0,
            "solar_power_in_space": None,
            "surface_properties": _planet_surface_props(sp_surface, defaults),
            "starmap_distance_to_nauvis": None,
            "trip_time_to_nauvis_seconds": None,
            "native_resources": [],
            "native_entities": [],
            "lacks": ["water", "trees", "wood", "stone", "iron-ore",
                      "copper-ore", "coal", "uranium-ore", "crude-oil"],
            "from_mod": "space-age",
        })

    # Solar-system-edge & shattered-planet (space-locations) - include for completeness
    for loc_name, loc in dump.get("space-location", {}).items():
        if loc.get("hidden") or loc_name == "space-location-unknown":
            continue
        out.append({
            "name": loc_name,
            "type": "space-location",
            "starmap_distance": loc.get("distance"),
            "starmap_orientation": loc.get("orientation"),
            "starmap_magnitude": loc.get("magnitude"),
            "gravity_pull": loc.get("gravity_pull"),
            "solar_power_in_space": loc.get("solar_power_in_space"),
            "surface_properties": {},
            "starmap_distance_to_nauvis": None,
            "trip_time_to_nauvis_seconds": None,
            "native_resources": [],
            "native_entities": [],
            "lacks": [],
            "from_mod": "space-age",
        })

    return out


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def build_quality(dump: dict[str, Any]) -> list[dict[str, Any]]:
    """Quality tiers, ordered by `level`. Excludes the hidden
    `quality-unknown` UI placeholder.

    Per-quality multipliers visible in the dump:
      * beacon_power_usage_multiplier
      * mining_drill_resource_drain_multiplier
      * science_pack_drain_multiplier

    Other multipliers (machine speed, module strength, beacon strength)
    are NOT stored on the quality prototype itself in 2.0; they are
    hard-coded engine constants. The prototype `level` field uses the
    wide spacing 0/2/4/6/10 (not 0..4), but the gameplay rank that
    drives stat multipliers is the ordinal (0..4 or "rank" 0..5).
    Confirmed by reading the prototypes in the dump:
      normal=0, uncommon=2, rare=4, epic=6, legendary=10.

    Stat multipliers (engine constants, well-documented and consistent
    with the dumped beacon_power_usage_multiplier table):
      machine speed         : 1 + 0.3 * rank  (legendary=2.5)
      module effect          : same as machine speed
      beacon transmission    : same as machine speed
      stack-size on module-like items: 1.0 (modules don't stack-bonus)

    Quality "rank" (1..5 for non-normal) is used by the engine; the
    prototype `level` field is purely a sort key with non-linear
    spacing reserved for future tiers (e.g. infinite-quality-tiers mod
    inserts levels between epic and legendary).
    """
    out: list[dict[str, Any]] = []
    qualities = dump.get("quality", {})
    # Order by level to assign ranks 0..N
    ordered = sorted(
        ((n, q) for n, q in qualities.items()
         if not q.get("hidden") and n != "quality-unknown"),
        key=lambda kv: kv[1].get("level", 0),
    )
    for rank, (name, q) in enumerate(ordered):
        # Engine formula: stat bonuses scale with `level / 2`, NOT
        # with rank. Verified by reproducing the dump's
        # beacon_power_usage_multiplier values:
        #   uncommon level=2 -> (6-1)/6 = 0.8333
        #   rare     level=4 -> (6-2)/6 = 0.6667
        #   epic     level=6 -> (6-3)/6 = 0.5
        #   legendary level=10 -> (6-5)/6 = 0.1667
        # Every level/2 step adds 30 % to machine speed, module
        # effect strength, and beacon transmission, so legendary
        # (level=10) lands at 1 + 5*0.3 = 2.5 x.
        level = q.get("level", 0)
        scale_steps = level / 2
        speed_mult = 1.0 + 0.3 * scale_steps
        out.append({
            "name": name,
            "level": q.get("level", 0),
            "rank": rank,                   # 0=normal, 4=legendary
            "color": q.get("color"),
            "next": q.get("next"),
            "next_probability": q.get("next_probability"),
            "machine_speed_multiplier": round(speed_mult, 4),
            "module_effect_multiplier": round(speed_mult, 4),
            "beacon_strength_multiplier": round(speed_mult, 4),
            "beacon_power_usage_multiplier":
                q.get("beacon_power_usage_multiplier", 1.0),
            "mining_drill_resource_drain_multiplier":
                q.get("mining_drill_resource_drain_multiplier", 1.0),
            "science_pack_drain_multiplier":
                q.get("science_pack_drain_multiplier", 1.0),
            "from_mod": "quality" if rank > 0 else "base",
        })
    return out


# ---------------------------------------------------------------------------
# Beacons
# ---------------------------------------------------------------------------

_BEACON_MOD_HINTS = {
    "beacon": ["AdjustableModule", "Li-Module-Fix", "base"],
    "beacon-fish": ["Li-Module-Fix"],
    "beacon-interface--beacon": ["beacon-interface"],
    "beacon-interface--beacon-tile": ["beacon-interface"],
}


def build_beacons(dump: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, b in dump.get("beacon", {}).items():
        eu_kw = parse_energy_to_kw(b.get("energy_usage"))
        heat_kw = parse_energy_to_kw(b.get("heating_energy"))
        # source mod: explicit map > name prefix > path scan
        if name in _BEACON_MOD_HINTS:
            from_mod = _BEACON_MOD_HINTS[name][0]
        else:
            from_mod = detect_mod_from_name(name, detect_mod_from_paths(b))
        out.append({
            "name": name,
            "module_slots": b.get("module_slots"),
            "supply_area_distance": b.get("supply_area_distance"),
            "distribution_effectivity": b.get("distribution_effectivity"),
            "distribution_effectivity_bonus_per_quality_level":
                b.get("distribution_effectivity_bonus_per_quality_level", 0),
            "profile": b.get("profile"),
            "profile_length": len(b.get("profile") or []),
            "allowed_effects": b.get("allowed_effects", []),
            "energy_usage_kw": eu_kw,
            "heating_energy_kw": heat_kw,
            "beacon_counter": b.get("beacon_counter", "total"),
            "effect_receiver": b.get("effect_receiver"),
            "from_mod": from_mod,
        })
    return out


# ---------------------------------------------------------------------------
# Surface-condition restrictions
# ---------------------------------------------------------------------------

def _planet_props_lookup(planets: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    return {p["name"]: p["surface_properties"] for p in planets}


def _conditions_match(props: dict[str, float], conds: list[dict[str, Any]]) -> bool:
    """A surface satisfies all conditions in the list (each is
    {property, min?, max?})."""
    for c in conds:
        prop = c.get("property")
        if prop is None or prop not in props:
            return False
        v = props[prop]
        if "min" in c and v < c["min"]:
            return False
        if "max" in c and v > c["max"]:
            return False
    return True


def build_recipe_restrictions(
    dump: dict[str, Any], planets: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    props = _planet_props_lookup(planets)
    for name, recipe in dump.get("recipe", {}).items():
        sc = recipe.get("surface_conditions")
        if not sc:
            continue
        allowed = [pname for pname, p in props.items() if _conditions_match(p, sc)]
        out[name] = {
            "surface_conditions": sc,
            "allowed_planets": sorted(allowed),
        }
    return out


def build_entity_restrictions(
    dump: dict[str, Any], planets: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    props = _planet_props_lookup(planets)
    skip_types = {"explosion"}  # cosmetic, not placeable
    for typ, by_name in dump.items():
        if typ in skip_types or not isinstance(by_name, dict):
            continue
        for name, proto in by_name.items():
            if not isinstance(proto, dict):
                continue
            sc = proto.get("surface_conditions")
            if not sc:
                continue
            allowed = [pname for pname, p in props.items() if _conditions_match(p, sc)]
            out[name] = {
                "type": typ,
                "surface_conditions": sc,
                "allowed_planets": sorted(allowed),
            }
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--dump", type=Path, default=DEFAULT_DUMP,
                    help="path to data-raw-dump.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="output directory")
    ap.add_argument("--human", action="store_true",
                    help="also print a one-line summary")
    args = ap.parse_args(argv)

    if not args.dump.is_file():
        print(f"error: dump not found at {args.dump}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    with args.dump.open() as f:
        dump = json.load(f)

    planets = build_planets(dump)
    quality = build_quality(dump)
    beacons = build_beacons(dump)
    recipe_restr = build_recipe_restrictions(dump, planets)
    entity_restr = build_entity_restrictions(dump, planets)

    _write_json(args.out / "planets.json", planets)
    _write_json(args.out / "quality.json", quality)
    _write_json(args.out / "beacons.json", beacons)
    _write_json(args.out / "recipe_planet_restrictions.json", recipe_restr)
    _write_json(args.out / "entity_planet_restrictions.json", entity_restr)

    if args.human:
        n_planets = sum(1 for p in planets if p["type"] == "planet")
        n_surfaces = sum(1 for p in planets if p["type"] == "surface")
        n_quality = len(quality)
        n_beacons = len(beacons)
        print(
            f"wrote planets.json (planets={n_planets} + surface={n_surfaces} + "
            f"locs={len(planets)-n_planets-n_surfaces}), "
            f"quality.json ({n_quality} tiers), "
            f"beacons.json ({n_beacons} beacons), "
            f"recipe_planet_restrictions.json ({len(recipe_restr)}), "
            f"entity_planet_restrictions.json ({len(entity_restr)})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
