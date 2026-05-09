#!/usr/bin/env python3
"""
extract_logistics.py - Logistics-domain prototype extractor for Factorio.

Reads specs/data-raw-dump.json (the live --dump-data output of the user's
install) and writes five JSON spec files under specs/:

  belts.json              transport-belt + underground-belt + splitter +
                          loader (2x1) + loader-1x1, with throughput math
  inserters.json          every inserter, with rotation/extension speed,
                          stack size, energy use
  electric_network.json   poles, accumulators, solar, boilers/generators,
                          reactors, fusion
  robots.json             logistic-robot + construction-robot + roboport
  research_effects.json   every technology that mutates an entity stat,
                          with prerequisites and (for infinite techs) the
                          science-pack count formula

Pure stdlib. Run from the repo root or anywhere; output paths are relative
to the script's location.

Speeds and rates are reported in raw (tiles/tick) and human (items/s,
items/min, kW, MJ) units side by side. Factorio runs at 60 update ticks
per second; one belt tile holds 8 items per lane (4 per side, 2 sides).

Mod origin is inferred from the prototype's icon path: a `__foo__/...`
prefix means the prototype was added by mod `foo`. Base game prototypes
that mods *modify* in place (e.g. logistic-robot speed under
Better_Robots_Plus) still report `from_mod=base`; their stat values in
the dump already reflect those mod overrides.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP_PATH = os.path.join(REPO_ROOT, "specs", "data-raw-dump.json")
OUT_DIR = os.path.join(REPO_ROOT, "specs")

TICKS_PER_SECOND = 60
ITEMS_PER_BELT_TILE_PER_LANE = 8  # Factorio belt model: 8 item slots per tile per side


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

_ENERGY_RE = re.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z]*)\s*$")
_UNIT_TO_W = {
    "": 1.0,
    "w": 1.0,
    "kw": 1e3,
    "mw": 1e6,
    "gw": 1e9,
    "tw": 1e12,
}
_UNIT_TO_J = {
    "": 1.0,
    "j": 1.0,
    "kj": 1e3,
    "mj": 1e6,
    "gj": 1e9,
    "tj": 1e12,
}


def parse_energy(value: Any, kind: str = "power") -> Optional[float]:
    """Parse a Factorio energy string ('20MW', '5kJ', '0.4kW').

    `kind` selects the SI table: 'power' (W) or 'energy' (J). Returns the
    numeric value in the table's base unit (W or J), or None if `value`
    is None / unparseable.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    m = _ENERGY_RE.match(s)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2).lower()
    table = _UNIT_TO_W if kind == "power" else _UNIT_TO_J
    if unit not in table:
        # Unknown unit; return raw number so caller can decide.
        return num
    return num * table[unit]


def icon_str(entity: Dict[str, Any]) -> str:
    """Best-effort extract of the entity's icon path."""
    ic = entity.get("icon")
    if isinstance(ic, str):
        return ic
    icons = entity.get("icons")
    if isinstance(icons, list) and icons:
        first = icons[0]
        if isinstance(first, dict) and isinstance(first.get("icon"), str):
            return first["icon"]
    return ""


_MOD_RE = re.compile(r"__([A-Za-z0-9_-]+)__")

# Map raw mod-token to a friendlier label used in the spec output.
_MOD_LABEL = {
    "base": "base",
    "core": "base",
    "space-age": "space-age",
    "quality": "quality",
    "elevated-rails": "elevated-rails",
}


def from_mod(entity: Dict[str, Any]) -> str:
    """Infer originating mod from an entity's icon path."""
    m = _MOD_RE.search(icon_str(entity))
    if not m:
        return "unknown"
    token = m.group(1)
    return _MOD_LABEL.get(token, token)


def round_clean(x: Optional[float], digits: int = 6) -> Optional[float]:
    """Round to N digits and drop trailing zeros to keep JSON readable."""
    if x is None:
        return None
    if not isinstance(x, (int, float)):
        return x
    r = round(float(x), digits)
    # Convert -0.0 to 0.0
    if r == 0:
        r = 0.0
    return r


def write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Belts
# ---------------------------------------------------------------------------


def belt_throughput(speed_tiles_per_tick: float) -> Tuple[float, float]:
    """Return (items/s/lane, items/s total) for a Factorio belt.

    speed * 60 ticks * 8 items per tile per lane = items/s/lane.
    Two lanes per belt, so total = 2 * per_lane.
    """
    per_lane = speed_tiles_per_tick * TICKS_PER_SECOND * ITEMS_PER_BELT_TILE_PER_LANE
    return per_lane, per_lane * 2.0


def extract_belts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # Underground belts: include max_distance.
    underground_max = {}
    for name, e in (raw.get("underground-belt") or {}).items():
        underground_max[name] = e.get("max_distance")

    def emit(name: str, e: Dict[str, Any], proto_type: str,
             extra: Optional[Dict[str, Any]] = None) -> None:
        speed = e.get("speed")
        per_lane, total = belt_throughput(speed) if speed is not None else (None, None)
        rec = {
            "name": name,
            "type": proto_type,
            "speed_tiles_per_tick": round_clean(speed),
            "items_per_second_per_lane": round_clean(per_lane, 4),
            "items_per_second_total": round_clean(total, 4),
            "items_per_minute_total": round_clean(total * 60.0 if total is not None else None, 2),
            "underground_max_distance": None,
            "from_mod": from_mod(e),
        }
        if extra:
            rec.update(extra)
        out.append(rec)

    # transport-belt: link to its matching underground tier for convenience.
    for name, e in (raw.get("transport-belt") or {}).items():
        related = e.get("related_underground_belt")
        emit(name, e, "transport-belt", {
            "related_underground_belt": related,
            "underground_max_distance": underground_max.get(related),
        })

    # underground-belt: stash own max_distance.
    for name, e in (raw.get("underground-belt") or {}).items():
        emit(name, e, "underground-belt", {
            "underground_max_distance": e.get("max_distance"),
        })

    # splitter: same speed, no underground field.
    for name, e in (raw.get("splitter") or {}).items():
        emit(name, e, "splitter")

    # loader (2x1): legacy/base.
    for name, e in (raw.get("loader") or {}).items():
        emit(name, e, "loader")

    # loader-1x1: includes vanilla 1x1 + loaders-modernized variants.
    for name, e in (raw.get("loader-1x1") or {}).items():
        emit(name, e, "loader-1x1", {
            "container_distance": e.get("container_distance"),
        })

    return out


# ---------------------------------------------------------------------------
# Inserters
# ---------------------------------------------------------------------------


def _hand_radius(pos: Any) -> Optional[float]:
    """Distance from inserter centre to pickup/insert position (tiles)."""
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        return None
    try:
        x = float(pos[0]); y = float(pos[1])
    except (TypeError, ValueError):
        return None
    # Factorio reports as [dx, dy] from entity centre. Use Euclidean.
    return (x * x + y * y) ** 0.5


def extract_inserters(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name, e in (raw.get("inserter") or {}).items():
        es = e.get("energy_source") or {}
        drain_w = parse_energy(es.get("drain"), "power") if es.get("type") == "electric" else None
        rot = e.get("rotation_speed")
        ext = e.get("extension_speed")
        # Quarter-turn (90 degrees) takes 0.25 / rotation_speed ticks because
        # rotation_speed is in revolutions/tick (1.0 = full turn per tick).
        quarter_turn_ticks = round_clean(0.25 / rot, 4) if rot else None
        rec = {
            "name": name,
            "type": "inserter",
            "rotation_speed_rev_per_tick": round_clean(rot, 6),
            "extension_speed_tiles_per_tick": round_clean(ext, 6),
            "quarter_turn_ticks": quarter_turn_ticks,
            "default_stack_size": 1,
            "stack_size_bonus": e.get("stack_size_bonus", 0),
            "is_bulk": bool(e.get("bulk")),
            "filter_count": e.get("filter_count", 0),
            "energy_per_movement_kj": round_clean(
                (parse_energy(e.get("energy_per_movement"), "energy") or 0) / 1e3, 4),
            "energy_per_rotation_kj": round_clean(
                (parse_energy(e.get("energy_per_rotation"), "energy") or 0) / 1e3, 4),
            "drain_kw": round_clean((drain_w or 0) / 1e3, 4) if drain_w is not None else None,
            "energy_source_type": es.get("type"),
            "pickup_position": e.get("pickup_position"),
            "insert_position": e.get("insert_position"),
            "pickup_distance_tiles": round_clean(_hand_radius(e.get("pickup_position")), 3),
            "insert_distance_tiles": round_clean(_hand_radius(e.get("insert_position")), 3),
            "from_mod": from_mod(e),
        }
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Electric network: poles, accumulators, solar, boilers, generators, reactors
# ---------------------------------------------------------------------------


def extract_electric(raw: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    poles: List[Dict[str, Any]] = []
    for name, e in (raw.get("electric-pole") or {}).items():
        sad = e.get("supply_area_distance")
        # supply_area_distance is the half-side of the supply square (tiles
        # from the pole centre). Square edge = 2 * supply_area_distance.
        square = (sad * 2) if isinstance(sad, (int, float)) else None
        poles.append({
            "name": name,
            "type": "electric-pole",
            "supply_area_radius_tiles": sad,
            "supply_area_square_tiles": square,
            "wire_reach_tiles": e.get("maximum_wire_distance"),
            "max_health": e.get("max_health"),
            "from_mod": from_mod(e),
        })

    accumulators: List[Dict[str, Any]] = []
    for name, e in (raw.get("accumulator") or {}).items():
        es = e.get("energy_source") or {}
        accumulators.append({
            "name": name,
            "type": "accumulator",
            "energy_capacity_mj": round_clean(
                (parse_energy(es.get("buffer_capacity"), "energy") or 0) / 1e6, 4),
            "input_flow_kw": round_clean(
                (parse_energy(es.get("input_flow_limit"), "power") or 0) / 1e3, 4),
            "output_flow_kw": round_clean(
                (parse_energy(es.get("output_flow_limit"), "power") or 0) / 1e3, 4),
            "max_health": e.get("max_health"),
            "from_mod": from_mod(e),
        })

    solar: List[Dict[str, Any]] = []
    for name, e in (raw.get("solar-panel") or {}).items():
        prod_w = parse_energy(e.get("production"), "power")
        solar.append({
            "name": name,
            "type": "solar-panel",
            "production_kw_peak": round_clean((prod_w or 0) / 1e3, 4),
            "average_kw_nauvis": round_clean((prod_w or 0) / 1e3 * 0.7, 4),
            "from_mod": from_mod(e),
        })

    boilers: List[Dict[str, Any]] = []
    for name, e in (raw.get("boiler") or {}).items():
        cons = parse_energy(e.get("energy_consumption"), "power")
        boilers.append({
            "name": name,
            "type": "boiler",
            "energy_consumption_mw": round_clean((cons or 0) / 1e6, 4),
            "target_temperature_c": e.get("target_temperature"),
            "mode": e.get("mode"),
            "from_mod": from_mod(e),
        })

    generators: List[Dict[str, Any]] = []
    for name, e in (raw.get("generator") or {}).items():
        # Steam engine / turbine. max_power is fluid_usage_per_tick * 60 *
        # (max_temp - 15) * specific-heat-of-steam (200 J/unit/deg) * effectivity.
        # Factorio computes that internally; we just expose the inputs.
        generators.append({
            "name": name,
            "type": "generator",
            "effectivity": e.get("effectivity"),
            "fluid_usage_per_tick": e.get("fluid_usage_per_tick"),
            "maximum_temperature_c": e.get("maximum_temperature"),
            "max_power_output_mw": round_clean(
                (parse_energy(e.get("max_power_output"), "power") or 0) / 1e6, 4)
                if e.get("max_power_output") is not None else None,
            "from_mod": from_mod(e),
        })

    reactors: List[Dict[str, Any]] = []
    for name, e in (raw.get("reactor") or {}).items():
        cons = parse_energy(e.get("consumption"), "power")
        reactors.append({
            "name": name,
            "type": "reactor",
            "consumption_mw": round_clean((cons or 0) / 1e6, 4),
            "neighbour_bonus": e.get("neighbour_bonus"),
            "max_health": e.get("max_health"),
            "energy_source_type": (e.get("energy_source") or {}).get("type"),
            "from_mod": from_mod(e),
        })

    fusion_reactors: List[Dict[str, Any]] = []
    for name, e in (raw.get("fusion-reactor") or {}).items():
        pi = parse_energy(e.get("power_input"), "power")
        fusion_reactors.append({
            "name": name,
            "type": "fusion-reactor",
            "power_input_mw": round_clean((pi or 0) / 1e6, 4),
            "max_fluid_usage": e.get("max_fluid_usage"),
            "two_direction_only": e.get("two_direction_only"),
            "perceived_performance": e.get("perceived_performance"),
            "max_health": e.get("max_health"),
            "from_mod": from_mod(e),
        })

    fusion_generators: List[Dict[str, Any]] = []
    for name, e in (raw.get("fusion-generator") or {}).items():
        fusion_generators.append({
            "name": name,
            "type": "fusion-generator",
            "max_fluid_usage": e.get("max_fluid_usage"),
            "perceived_performance": e.get("perceived_performance"),
            "max_health": e.get("max_health"),
            "from_mod": from_mod(e),
        })

    return {
        "poles": poles,
        "accumulators": accumulators,
        "solar_panels": solar,
        "boilers": boilers,
        "generators": generators,
        "reactors": reactors,
        "fusion_reactors": fusion_reactors,
        "fusion_generators": fusion_generators,
    }


# ---------------------------------------------------------------------------
# Robots and roboports
# ---------------------------------------------------------------------------


def _robot_record(name: str, e: Dict[str, Any], proto_type: str) -> Dict[str, Any]:
    energy_per_tick_w = parse_energy(e.get("energy_per_tick"), "power")
    # energy_per_tick is reported as 'NkJ' — the units string treats J/tick
    # as power-equivalent. Game logic: bot drains energy_per_tick joules
    # every tick while flying. So convert via parse_energy(..., 'energy').
    energy_per_tick_j = parse_energy(e.get("energy_per_tick"), "energy")
    energy_per_move_j = parse_energy(e.get("energy_per_move"), "energy")
    max_energy_j = parse_energy(e.get("max_energy"), "energy")
    speed_tt = e.get("speed")
    return {
        "name": name,
        "type": proto_type,
        "max_speed_tiles_per_tick": round_clean(speed_tt, 6),
        "max_speed_tiles_per_second": round_clean(speed_tt * 60 if speed_tt else None, 4),
        "max_payload_size": e.get("max_payload_size"),
        "energy_per_tick_j": round_clean(energy_per_tick_j, 4),
        "energy_per_move_j": round_clean(energy_per_move_j, 4),
        "max_energy_kj": round_clean((max_energy_j or 0) / 1e3, 4) if max_energy_j else None,
        "min_to_charge_fraction": e.get("min_to_charge"),
        "max_to_charge_fraction": e.get("max_to_charge"),
        "speed_multiplier_when_out_of_energy": e.get("speed_multiplier_when_out_of_energy"),
        "from_mod": from_mod(e),
    }


def extract_robots(raw: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    bots: List[Dict[str, Any]] = []
    for name, e in (raw.get("logistic-robot") or {}).items():
        bots.append(_robot_record(name, e, "logistic-robot"))
    for name, e in (raw.get("construction-robot") or {}).items():
        bots.append(_robot_record(name, e, "construction-robot"))

    roboports: List[Dict[str, Any]] = []
    for name, e in (raw.get("roboport") or {}).items():
        es = e.get("energy_source") or {}
        roboports.append({
            "name": name,
            "type": "roboport",
            "logistics_radius_tiles": e.get("logistics_radius"),
            "construction_radius_tiles": e.get("construction_radius"),
            "robot_slots_count": e.get("robot_slots_count"),
            "material_slots_count": e.get("material_slots_count"),
            "charging_station_count": len(e.get("charging_offsets") or []),
            "charging_energy_mw": round_clean(
                (parse_energy(e.get("charging_energy"), "power") or 0) / 1e6, 4),
            "input_flow_limit_mw": round_clean(
                (parse_energy(es.get("input_flow_limit"), "power") or 0) / 1e6, 4),
            "buffer_capacity_mj": round_clean(
                (parse_energy(es.get("buffer_capacity"), "energy") or 0) / 1e6, 4),
            "energy_usage_kw": round_clean(
                (parse_energy(e.get("energy_usage"), "power") or 0) / 1e3, 4),
            "recharge_minimum_mj": round_clean(
                (parse_energy(e.get("recharge_minimum"), "energy") or 0) / 1e6, 4),
            "from_mod": from_mod(e),
        })

    return {"robots": bots, "roboports": roboports}


# ---------------------------------------------------------------------------
# Research effects
# ---------------------------------------------------------------------------

# Effect types we care about: anything that mutates an entity stat. Skip
# unlock-recipe (handled by the recipes spec) and unlock-* one-shots.
_EFFECT_INTEREST = {
    "inserter-stack-size-bonus",
    "bulk-inserter-capacity-bonus",
    "belt-stack-size-bonus",
    "worker-robot-speed",
    "worker-robot-storage",
    "worker-robot-battery",
    "mining-drill-productivity-bonus",
    "mining-productivity-bonus",  # legacy alias; kept for safety
    "laboratory-speed",
    "laboratory-productivity",
    "character-inventory-slots-bonus",
    "character-logistic-trash-slots",
    "character-logistic-requests",
    "character-mining-speed",
    "character-health-bonus",
    "maximum-following-robots-count",
    "follower-robot-count",
    "train-braking-force-bonus",
    "artillery-range",
    "ammo-damage",
    "gun-speed",
    "turret-attack",
    "change-recipe-productivity",
    "vehicle-logistics",
    "create-ghost-on-entity-death",
    "cliff-deconstruction-enabled",
    "mining-with-fluid",
    "rail-planner-allow-elevated-rails",
    "rail-support-on-deep-oil-ocean",
    "unlock-circuit-network",
    "unlock-quality",
    "unlock-space-platforms",
    "unlock-space-location",
    "nothing",
}


def extract_research_effects(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    techs = raw.get("technology") or {}
    for tname, t in techs.items():
        effects = t.get("effects") or []
        if not effects:
            continue
        unit = t.get("unit") or {}
        max_level = t.get("max_level")
        infinite = max_level == "infinite" or "count_formula" in unit
        count_formula = unit.get("count_formula") if infinite else None
        flat_count = unit.get("count")
        ingredients = unit.get("ingredients")
        time = unit.get("time")
        prereqs = t.get("prerequisites") or []

        for eff in effects:
            etype = eff.get("type")
            if etype not in _EFFECT_INTEREST:
                continue
            rec: Dict[str, Any] = {
                "tech_name": tname,
                "effect_type": etype,
                "infinite": bool(infinite),
                "max_level": max_level,
                "count_formula": count_formula,
                "flat_count": flat_count,
                "time_per_unit": time,
                "ingredients": ingredients,
                "prerequisites": prereqs,
            }
            # Modifier shape varies by effect type.
            if "modifier" in eff:
                rec["modifier"] = eff["modifier"]
            if "change" in eff:
                # change-recipe-productivity uses "change" instead of "modifier".
                rec["modifier"] = eff["change"]
            if "recipe" in eff:
                rec["recipe"] = eff["recipe"]
            if "ammo_category" in eff:
                rec["ammo_category"] = eff["ammo_category"]
            if "turret_id" in eff:
                rec["turret_id"] = eff["turret_id"]
            if "effect_description" in eff:
                rec["effect_description"] = eff["effect_description"]
            out.append(rec)

    # Stable sort: tech name then effect type then recipe.
    out.sort(key=lambda r: (r["tech_name"], r["effect_type"], r.get("recipe") or ""))
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dump", default=DUMP_PATH,
                    help=f"path to data-raw-dump.json (default: {DUMP_PATH})")
    ap.add_argument("--out-dir", default=OUT_DIR,
                    help=f"output directory (default: {OUT_DIR})")
    ap.add_argument("--quiet", action="store_true", help="suppress per-file summary")
    args = ap.parse_args(argv)

    if not os.path.exists(args.dump):
        print(f"error: dump not found at {args.dump}", file=sys.stderr)
        print("       run tools/dump_prototypes.sh to generate it", file=sys.stderr)
        return 1

    with open(args.dump, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    belts = extract_belts(raw)
    inserters = extract_inserters(raw)
    electric = extract_electric(raw)
    robots = extract_robots(raw)
    research = extract_research_effects(raw)

    write_json(os.path.join(args.out_dir, "belts.json"), belts)
    write_json(os.path.join(args.out_dir, "inserters.json"), inserters)
    write_json(os.path.join(args.out_dir, "electric_network.json"), electric)
    write_json(os.path.join(args.out_dir, "robots.json"), robots)
    write_json(os.path.join(args.out_dir, "research_effects.json"), research)

    if not args.quiet:
        print(f"belts.json:             {len(belts)} entries")
        print(f"inserters.json:         {len(inserters)} entries")
        print(f"electric_network.json:  {sum(len(v) for v in electric.values())} entries "
              f"across {len(electric)} groups")
        print(f"robots.json:            {len(robots['robots'])} robots, "
              f"{len(robots['roboports'])} roboports")
        print(f"research_effects.json:  {len(research)} effects "
              f"across {len(set(r['tech_name'] for r in research))} techs")

    return 0


if __name__ == "__main__":
    sys.exit(main())
