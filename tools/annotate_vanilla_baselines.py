#!/usr/bin/env python3
"""Annotate spec JSON files with vanilla 2.0.76 baselines where the user's
modded values diverge from stock.

Stdlib only. Re-runnable: it overwrites only the `vanilla_2_0_76` field.

Source of truth for vanilla numbers: the Factorio Wiki (cross-checked
against Space Age 2.0 Quality DLC documentation), captured manually here
because the dump itself reflects mods, not vanilla.

Run from repo root:
    python3 tools/annotate_vanilla_baselines.py
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SPECS = REPO / "specs"

# Vanilla 2.0.76 + Space Age + Quality + Elevated Rails (no third-party mods).
# Each entry lists ONLY the fields that diverge from the user's dump; sibling
# spec fields are left as-is.

VANILLA_MACHINES: dict[str, dict] = {
    # type: assembling-machine
    "assembling-machine-1": {"module_slots": 0, "base_effect": {}},
    "assembling-machine-2": {"module_slots": 2, "base_effect": {}},
    "assembling-machine-3": {"module_slots": 4, "base_effect": {}},
    "oil-refinery":         {"module_slots": 3, "base_effect": {}},
    "chemical-plant":       {"module_slots": 3, "base_effect": {}},
    "centrifuge":           {"module_slots": 2, "base_effect": {}},
    "crusher":              {"module_slots": 2, "base_effect": {}},
    "foundry":              {"module_slots": 4, "base_effect": {"productivity": 0.5}},
    "electromagnetic-plant":{"module_slots": 5, "base_effect": {"productivity": 0.5}},
    "biochamber":           {"module_slots": 4, "base_effect": {"productivity": 0.5}},
    "cryogenic-plant":      {"module_slots": 8, "base_effect": {}},
    "captive-biter-spawner":{"module_slots": 1, "base_effect": {}},
    "rocket-silo":          {"module_slots": 4, "base_effect": {}},
    # type: furnace
    "stone-furnace":        {"module_slots": 0, "base_effect": {}},
    "steel-furnace":        {"module_slots": 0, "base_effect": {}},
    "electric-furnace":     {"module_slots": 2, "base_effect": {}},
    "recycler":             {
        "module_slots": 4,
        "base_effect": {},
        "allowed_effects": ["consumption", "speed", "pollution", "quality"],
        "note": "vanilla recycler explicitly disallows productivity",
    },
    # type: mining-drill
    "burner-mining-drill":  {"module_slots": 0, "base_effect": {}},
    "electric-mining-drill":{"module_slots": 3, "base_effect": {}},
    "pumpjack":             {"module_slots": 2, "base_effect": {}},
    "big-mining-drill":     {"module_slots": 4, "base_effect": {}},
    # type: lab
    "lab":                  {"module_slots": 2, "base_effect": {}},
    "biolab":               {"module_slots": 4, "base_effect": {"productivity": 0.5}},
    # type: agricultural-tower
    # cultivators are mod prototypes; no vanilla baseline
}

# Vanilla allowed_effects for crafters (everything except recycler is the same):
# vanilla allows: consumption, speed, productivity, pollution, quality
# (productivity gating is per-recipe via allow_productivity, not per-machine)

VANILLA_BEACON: dict = {
    "module_slots": 2,
    "supply_area_distance": 3,
    "distribution_effectivity": 1.5,
    "distribution_effectivity_bonus_per_quality_level": 0.5,
    "allowed_effects": ["consumption", "speed", "pollution"],
    "energy_usage_kw": 480.0,
    "effect_receiver": {},
    "note": (
        "vanilla 2.0 beacon: 2 slots, 1.5 effectivity, 9x9 supply area "
        "(half-side 3 = 6+3 == 9 inclusive); no productivity, no quality, "
        "no base_effect. The `profile` array is identical (1/sqrt(N))."
    ),
}

VANILLA_ROBOTS: dict[str, dict] = {
    "logistic-robot": {
        "max_speed_tiles_per_tick": 0.05,
        "max_speed_tiles_per_second": 3.0,
        "max_payload_size": 1,
        "max_payload_via_research": 4,
        "energy_per_tick_j": 4.0,
        "energy_per_move_j": 5000.0,
        "max_energy_kj": 1500.0,
        "note": (
            "vanilla 2.0 logistic-robot: 0.05 tile/tick base speed, payload "
            "1 (research worker_robot_storage tops out at 4). Energy per "
            "tick/move and battery from base prototype."
        ),
    },
    "construction-robot": {
        "max_speed_tiles_per_tick": 0.06,
        "max_speed_tiles_per_second": 3.6,
        "max_payload_size": 1,
        "max_payload_via_research": 4,
        "energy_per_tick_j": 2.0,
        "energy_per_move_j": 5000.0,
        "max_energy_kj": 1500.0,
        "note": (
            "vanilla 2.0 construction-robot: 0.06 tile/tick (~3.6 tiles/s) "
            "base speed, payload 1 (research raises to 4)."
        ),
    },
}

VANILLA_ROBOPORT: dict = {
    "logistics_radius_tiles": 50,
    "construction_radius_tiles": 110,
    "robot_slots_count": 7,
    "material_slots_count": 7,
    "charging_station_count": 4,
    "charging_energy_mw": 4.0,
    "input_flow_limit_mw": 5.0,
    "buffer_capacity_mj": 100.0,
    "energy_usage_kw": 50.0,
    "recharge_minimum_mj": 40.0,
    "note": (
        "vanilla 2.0 roboport: 4 charging stations at 4 MW each, 5 MW "
        "input cap, 100 MJ buffer. The user's BetterRoboport mod overrides "
        "this to 16/20/80/2500."
    ),
}


def annotate_machines(path: pathlib.Path) -> int:
    data = json.loads(path.read_text())
    changed = 0
    for entry in data:
        name = entry.get("name")
        if name in VANILLA_MACHINES:
            entry["vanilla_2_0_76"] = VANILLA_MACHINES[name]
            changed += 1
        else:
            # Strip a stale annotation if the prototype is no longer in the table
            entry.pop("vanilla_2_0_76", None)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return changed


def annotate_beacons(path: pathlib.Path) -> int:
    data = json.loads(path.read_text())
    changed = 0
    for entry in data:
        if entry.get("name") == "beacon":
            entry["vanilla_2_0_76"] = VANILLA_BEACON
            changed += 1
        else:
            entry.pop("vanilla_2_0_76", None)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return changed


def annotate_robots(path: pathlib.Path) -> int:
    data = json.loads(path.read_text())
    robots_changed = 0
    for entry in data.get("robots", []):
        name = entry.get("name")
        if name in VANILLA_ROBOTS:
            entry["vanilla_2_0_76"] = VANILLA_ROBOTS[name]
            robots_changed += 1
        else:
            entry.pop("vanilla_2_0_76", None)
    roboport_changed = 0
    for entry in data.get("roboports", []):
        if entry.get("name") == "roboport":
            entry["vanilla_2_0_76"] = VANILLA_ROBOPORT
            roboport_changed += 1
        else:
            entry.pop("vanilla_2_0_76", None)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return robots_changed + roboport_changed


def main() -> int:
    if not SPECS.exists():
        print(f"specs directory not found at {SPECS}", file=sys.stderr)
        return 1
    n_machines = annotate_machines(SPECS / "machines.json")
    n_beacons = annotate_beacons(SPECS / "beacons.json")
    n_robots = annotate_robots(SPECS / "robots.json")
    print(
        f"annotated {n_machines} machines, {n_beacons} beacon entries, "
        f"{n_robots} robot/roboport entries with vanilla_2_0_76 field"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
