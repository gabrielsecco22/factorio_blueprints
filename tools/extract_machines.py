#!/usr/bin/env python3
"""extract_machines.py

Read specs/data-raw-dump.json (a Factorio prototype dump) and emit normalised
JSON catalogs into specs/:

  machines.json          crafting machines + special producers (mining drill,
                         boiler, generator, reactor, fusion generator,
                         agricultural tower, asteroid collector)
  recipes.json           every recipe prototype
  recipe_categories.json category -> list of machines that can craft it
  items.json             items + tools + modules + ammo + capsules + armor + guns
  fluids.json            every fluid prototype
  modules.json           module prototypes only

The script is stdlib-only and is safe to re-run.

Run from anywhere; paths are resolved relative to this file.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Iterable

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DUMP_PATH = os.path.join(ROOT, "specs", "data-raw-dump.json")
OUT_DIR = os.path.join(ROOT, "specs")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_ENERGY_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*([kMGTP]?)([WJ])\s*$"
)
_SI = {"": 1.0, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15}


def parse_energy_kw(value: Any) -> float | None:
    """Convert a Factorio energy string (e.g. ``"375kW"``, ``"40MW"``) into
    kilowatts.  Returns ``None`` if value is missing or unparseable.

    Numeric values are assumed to already be in watts.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    if not isinstance(value, str):
        return None
    m = _ENERGY_RE.match(value)
    if not m:
        return None
    n = float(m.group(1))
    mult = _SI.get(m.group(2), 1.0)
    watts = n * mult
    if m.group(3) == "J":
        # buffer/heat capacity expressed in joules: report joules directly
        # but caller only uses this for kW; return None for joules.
        return None
    return watts / 1000.0


def parse_energy_kj(value: Any) -> float | None:
    """Convert an energy string expressed in joules into kilojoules."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    if not isinstance(value, str):
        return None
    m = _ENERGY_RE.match(value)
    if not m:
        return None
    n = float(m.group(1))
    mult = _SI.get(m.group(2), 1.0)
    if m.group(3) != "J":
        return None
    return (n * mult) / 1000.0


_MOD_RE = re.compile(r"__([A-Za-z0-9_\-+]+)__/")


def from_mod(prototype: dict) -> str | None:
    """Heuristically derive the originating mod from any internal asset path
    (icon, sprite, sound).  Returns ``None`` if nothing identifiable.
    """
    for key in ("icon", "icons"):
        v = prototype.get(key)
        if isinstance(v, str):
            m = _MOD_RE.search(v)
            if m:
                return m.group(1)
        if isinstance(v, list):
            for entry in v:
                if isinstance(entry, dict):
                    s = entry.get("icon") or entry.get("filename")
                    if isinstance(s, str):
                        m = _MOD_RE.search(s)
                        if m:
                            return m.group(1)
    return None


def emissions_per_minute(es: dict | None) -> dict | None:
    if not isinstance(es, dict):
        return None
    epm = es.get("emissions_per_minute")
    if isinstance(epm, dict):
        return dict(epm)
    return None


def collision_size(prototype: dict) -> list[float] | None:
    """Tile footprint (width, height) derived from collision_box rounded up."""
    cb = prototype.get("collision_box")
    if (
        isinstance(cb, list)
        and len(cb) == 2
        and all(isinstance(p, list) and len(p) == 2 for p in cb)
    ):
        w = cb[1][0] - cb[0][0]
        h = cb[1][1] - cb[0][1]
        # Factorio rounds collision_box to nearest tile when placed
        return [int(round(w + 0.0001)) + (1 if (w - int(w)) > 0.5 else 0),
                int(round(h + 0.0001)) + (1 if (h - int(h)) > 0.5 else 0)]
    return None


def tile_size(prototype: dict) -> list[int] | None:
    if "tile_width" in prototype and "tile_height" in prototype:
        return [int(prototype["tile_width"]), int(prototype["tile_height"])]
    cb = prototype.get("collision_box")
    if (
        isinstance(cb, list)
        and len(cb) == 2
        and all(isinstance(p, list) and len(p) == 2 for p in cb)
    ):
        w = cb[1][0] - cb[0][0]
        h = cb[1][1] - cb[0][1]
        # Round up - integer tiles occupied
        return [int(w) + (1 if (w - int(w)) > 0.001 else 0),
                int(h) + (1 if (h - int(h)) > 0.001 else 0)]
    return None


def normalise_energy_source(es: dict | None) -> dict:
    """Trim noisy keys (smoke, light_flicker, sprites) but preserve
    semantically useful information.
    """
    if not isinstance(es, dict):
        return {"type": "none"}
    keep = {
        "type",
        "fuel_categories",
        "fuel_category",
        "effectivity",
        "fuel_inventory_size",
        "burnt_inventory_size",
        "drain",
        "burner_usage",
        "render_no_network_icon",
        "render_no_power_icon",
        "input_priority",
        "output_priority",
        "usage_priority",
        "buffer_capacity",
        "input_flow_limit",
        "output_flow_limit",
    }
    out: dict = {k: v for k, v in es.items() if k in keep}
    epm = emissions_per_minute(es)
    if epm is not None:
        out["emissions_per_minute"] = epm
    return out


def trim_fluid_box(fb: dict) -> dict:
    """Reduce a fluid_box to its semantically relevant fields."""
    keep = {
        "production_type",
        "volume",
        "filter",
        "minimum_temperature",
        "maximum_temperature",
        "secondary_draw_orders",
        "fluidbox_index",
        "pipe_connections",
    }
    out = {k: fb.get(k) for k in keep if k in fb}
    pcs = fb.get("pipe_connections") or []
    if pcs:
        # Strip per-connection art; keep position + direction
        slim = []
        for pc in pcs:
            if isinstance(pc, dict):
                slim.append({k: pc[k] for k in pc if k in (
                    "direction", "position", "flow_direction", "connection_type",
                )})
        out["pipe_connections"] = slim
    return out


def to_int_or_none(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# extractors
# --------------------------------------------------------------------------

# Prototype types we treat as "machines" for catalog purposes.
MACHINE_TYPES: tuple[str, ...] = (
    "assembling-machine",
    "furnace",
    "rocket-silo",
    "mining-drill",
    "boiler",
    "generator",
    "reactor",
    "fusion-generator",
    "fusion-reactor",
    "agricultural-tower",
    "asteroid-collector",
    "lab",
    "beacon",
)

# Item-like prototypes that should appear in items.json.
ITEM_TYPES: tuple[str, ...] = (
    "item",
    "tool",
    "module",
    "ammo",
    "capsule",
    "armor",
    "gun",
    "repair-tool",
    "rail-planner",
    "space-platform-starter-pack",
    "item-with-entity-data",
    "selection-tool",
    "spidertron-remote",
    # Blueprint-family items: also recyclable (have *-recycling recipes)
    # and so must be findable by name in items.json.
    "blueprint",
    "blueprint-book",
    "deconstruction-item",
    "upgrade-item",
    "copy-paste-tool",
)


def extract_machine(typ: str, ent: dict) -> dict:
    name = ent["name"]
    record: dict = {
        "name": name,
        "type": typ,
        "from_mod": from_mod(ent),
    }

    # Crafting categories: assembling/furnace/rocket-silo all share this field.
    cats = ent.get("crafting_categories")
    if cats is None and typ == "mining-drill":
        cats = None  # mining drills use resource_categories instead
    record["crafting_categories"] = list(cats) if isinstance(cats, list) else None

    if typ == "mining-drill":
        record["resource_categories"] = list(ent.get("resource_categories") or [])
        record["mining_speed"] = ent.get("mining_speed")
        record["crafting_speed"] = None
    else:
        record["crafting_speed"] = ent.get("crafting_speed")

    # Energy usage normalisation
    energy_field = (
        ent.get("energy_usage")
        or ent.get("energy_consumption")
        or ent.get("max_energy_usage")
        or ent.get("consumption")
    )
    record["energy_usage_kw"] = parse_energy_kw(energy_field)
    record["energy_usage_raw"] = energy_field

    es = ent.get("energy_source")
    record["energy_source"] = normalise_energy_source(es)
    # Surface drain when explicit
    drain_raw = (es or {}).get("drain") if isinstance(es, dict) else None
    record["drain_kw"] = parse_energy_kw(drain_raw)

    # Pollution / spores
    epm = emissions_per_minute(es)
    record["pollution"] = (epm or {}).get("pollution") if isinstance(epm, dict) else None
    record["emissions"] = epm

    # Modules
    record["module_slots"] = ent.get("module_slots", 0) if "module_slots" in ent else 0
    record["allowed_effects"] = list(ent.get("allowed_effects") or []) or None
    record["allowed_module_categories"] = list(
        ent.get("allowed_module_categories") or []
    ) or None

    # Inherent productivity / other base effects (foundry, EM plant, biochamber...)
    er = ent.get("effect_receiver") or {}
    if isinstance(er, dict):
        be = er.get("base_effect") or {}
        record["base_effect"] = dict(be) if isinstance(be, dict) else None
        record["uses_module_effects"] = er.get("uses_module_effects", True)
        record["uses_beacon_effects"] = er.get("uses_beacon_effects", True)
        record["uses_surface_effects"] = er.get("uses_surface_effects", True)
    else:
        record["base_effect"] = None
        record["uses_module_effects"] = True
        record["uses_beacon_effects"] = True
        record["uses_surface_effects"] = True

    # Fluid boxes
    fbs = ent.get("fluid_boxes")
    if isinstance(fbs, list):
        record["fluid_boxes"] = [trim_fluid_box(fb) for fb in fbs if isinstance(fb, dict)]
    elif "fluid_box" in ent or "input_fluid_box" in ent or "output_fluid_box" in ent:
        record["fluid_boxes"] = [
            trim_fluid_box(fb)
            for fb in (
                ent.get("fluid_box"),
                ent.get("input_fluid_box"),
                ent.get("output_fluid_box"),
            )
            if isinstance(fb, dict)
        ]
    else:
        record["fluid_boxes"] = []

    # Geometry
    record["tile_size"] = tile_size(ent)
    record["collision_box"] = ent.get("collision_box")
    record["selection_box"] = ent.get("selection_box")

    # Surface restrictions
    record["surface_conditions"] = ent.get("surface_conditions") or None

    # Special fields per machine type
    if typ == "rocket-silo":
        record["rocket_parts_required"] = ent.get("rocket_parts_required")
        record["fixed_recipe"] = ent.get("fixed_recipe")
        record["active_energy_usage_kw"] = parse_energy_kw(ent.get("active_energy_usage"))
        record["lamp_energy_usage_kw"] = parse_energy_kw(ent.get("lamp_energy_usage"))
    if typ in ("boiler",):
        record["target_temperature"] = ent.get("target_temperature")
        record["mode"] = ent.get("mode")
    if typ == "generator":
        record["fluid_usage_per_tick"] = ent.get("fluid_usage_per_tick")
        record["effectivity"] = ent.get("effectivity")
        record["maximum_temperature"] = ent.get("maximum_temperature")
    if typ in ("reactor", "fusion-reactor"):
        record["consumption_kw"] = parse_energy_kw(ent.get("consumption"))
        record["neighbour_bonus"] = ent.get("neighbour_bonus")
        hb = ent.get("heat_buffer") or {}
        if isinstance(hb, dict):
            record["heat_buffer_max_temp"] = hb.get("max_temperature")
            record["heat_buffer_specific_heat"] = hb.get("specific_heat")
    if typ == "fusion-generator":
        record["max_fluid_usage"] = ent.get("max_fluid_usage")
    if typ == "agricultural-tower":
        record["radius"] = ent.get("radius")
        record["crane_energy_usage_kw"] = parse_energy_kw(ent.get("crane_energy_usage"))
        record["input_inventory_size"] = ent.get("input_inventory_size")
    if typ == "asteroid-collector":
        record["collection_radius"] = ent.get("collection_radius")
        record["inventory_size"] = ent.get("inventory_size")
        record["arm_count_base"] = ent.get("arm_count_base")
        record["arm_speed_base"] = ent.get("arm_speed_base")
        record["passive_energy_usage_kw"] = parse_energy_kw(
            ent.get("passive_energy_usage")
        )
        record["arm_energy_usage_kw"] = parse_energy_kw(ent.get("arm_energy_usage"))
    if typ == "beacon":
        record["distribution_effectivity"] = ent.get("distribution_effectivity")
        record["distribution_effectivity_bonus_per_quality_level"] = ent.get(
            "distribution_effectivity_bonus_per_quality_level"
        )
        record["supply_area_distance"] = ent.get("supply_area_distance")
    if typ == "lab":
        record["researching_speed"] = ent.get("researching_speed")
        record["inputs"] = ent.get("inputs")

    # heating energy (Aquilo)
    if "heating_energy" in ent:
        record["heating_energy_kw"] = parse_energy_kw(ent.get("heating_energy"))

    # Burnt inventory & fuel categories duplicated for convenience
    if isinstance(es, dict) and es.get("type") == "burner":
        fc = es.get("fuel_categories") or (
            [es["fuel_category"]] if "fuel_category" in es else None
        )
        record["fuel_categories"] = fc

    return record


def extract_recipe(ent: dict) -> dict:
    name = ent["name"]
    record = {
        "name": name,
        "category": ent.get("category", "crafting"),
        "subgroup": ent.get("subgroup"),
        "ingredients": _normalise_ing_or_res(ent.get("ingredients", [])),
        "results": _normalise_ing_or_res(ent.get("results", [])),
        "energy_required": ent.get("energy_required", 0.5),
        "enabled": ent.get("enabled", True),
        "hidden": ent.get("hidden", False),
        "hidden_from_player_crafting": ent.get("hide_from_player_crafting", False),
        "allow_productivity": ent.get("allow_productivity", False),
        "allow_quality": ent.get("allow_quality", True),
        "allow_decomposition": ent.get("allow_decomposition", True),
        "main_product": ent.get("main_product"),
        "maximum_productivity": ent.get("maximum_productivity"),
        "surface_conditions": ent.get("surface_conditions") or None,
        "auto_recycle": ent.get("auto_recycle", True),
        "result_is_always_fresh": ent.get("result_is_always_fresh", False),
        "from_mod": from_mod(ent),
    }
    return record


def _normalise_ing_or_res(items: Iterable) -> list[dict]:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            # Legacy short form: ["item-name", amount]
            if isinstance(it, list) and len(it) == 2:
                out.append({"name": it[0], "amount": it[1], "type": "item"})
            continue
        rec = {
            "name": it.get("name"),
            "amount": it.get("amount"),
            "type": it.get("type", "item"),
        }
        for k in (
            "amount_min",
            "amount_max",
            "probability",
            "catalyst_amount",
            "minimum_temperature",
            "maximum_temperature",
            "temperature",
            "fluidbox_index",
            "ignored_by_stats",
            "ignored_by_productivity",
            "extra_count_fraction",
            "percent_spoiled",
        ):
            if k in it:
                rec[k] = it[k]
        out.append(rec)
    return out


def extract_item(typ: str, ent: dict) -> dict:
    return {
        "name": ent.get("name"),
        "type": typ,
        "stack_size": ent.get("stack_size"),
        "weight": ent.get("weight"),
        "place_result": ent.get("place_result"),
        "placed_as_equipment_result": ent.get("placed_as_equipment_result"),
        "fuel_value_kj": parse_energy_kj(ent.get("fuel_value")),
        "fuel_value_raw": ent.get("fuel_value"),
        "fuel_category": ent.get("fuel_category"),
        "fuel_categories": ent.get("fuel_categories"),
        "fuel_acceleration_multiplier": ent.get("fuel_acceleration_multiplier"),
        "fuel_top_speed_multiplier": ent.get("fuel_top_speed_multiplier"),
        "spoil_ticks": ent.get("spoil_ticks"),
        "spoil_result": ent.get("spoil_result"),
        "spoil_to_trigger_result": ent.get("spoil_to_trigger_result"),
        "send_to_orbit_mode": ent.get("send_to_orbit_mode"),
        "subgroup": ent.get("subgroup"),
        "from_mod": from_mod(ent),
    }


def extract_fluid(ent: dict) -> dict:
    return {
        "name": ent.get("name"),
        "default_temperature": ent.get("default_temperature"),
        "max_temperature": ent.get("max_temperature"),
        "heat_capacity_kj": parse_energy_kj(ent.get("heat_capacity")),
        "heat_capacity_raw": ent.get("heat_capacity"),
        "fuel_value_kj": parse_energy_kj(ent.get("fuel_value")),
        "fuel_value_raw": ent.get("fuel_value"),
        "gas_temperature": ent.get("gas_temperature"),
        "subgroup": ent.get("subgroup"),
        "from_mod": from_mod(ent),
    }


def extract_module(ent: dict) -> dict:
    return {
        "name": ent.get("name"),
        "category": ent.get("category"),
        "tier": ent.get("tier"),
        "effect": ent.get("effect") or {},
        "limitation": ent.get("limitation"),
        "limitation_blacklist": ent.get("limitation_blacklist"),
        "limitation_message_key": ent.get("limitation_message_key"),
        "stack_size": ent.get("stack_size"),
        "weight": ent.get("weight"),
        "from_mod": from_mod(ent),
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if not os.path.exists(DUMP_PATH):
        print(f"error: dump not found at {DUMP_PATH}", file=sys.stderr)
        return 2
    with open(DUMP_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    machines: list[dict] = []
    for typ in MACHINE_TYPES:
        block = data.get(typ) or {}
        for name in sorted(block):
            # beacon-interface-* are synthetic placeholders used by the
            # in-game beacon-interface mod for visualisation; not real entities.
            if name.startswith("beacon-interface--"):
                continue
            machines.append(extract_machine(typ, block[name]))

    recipes: list[dict] = []
    for name in sorted(data.get("recipe", {})):
        recipes.append(extract_recipe(data["recipe"][name]))

    # Cross-table: category -> machines that can produce it.
    cat_to_machines: dict[str, list[str]] = {}
    for m in machines:
        for cat in m.get("crafting_categories") or []:
            cat_to_machines.setdefault(cat, []).append(m["name"])
    # Also include resource categories for mining drills (kept under separate keys)
    resource_cat_to_drills: dict[str, list[str]] = {}
    for m in machines:
        for cat in m.get("resource_categories") or []:
            resource_cat_to_drills.setdefault(cat, []).append(m["name"])
    for v in cat_to_machines.values():
        v.sort()
    for v in resource_cat_to_drills.values():
        v.sort()
    recipe_categories_out = {
        "crafting_categories": dict(sorted(cat_to_machines.items())),
        "resource_categories": dict(sorted(resource_cat_to_drills.items())),
    }

    items: list[dict] = []
    seen_item_names: set[str] = set()
    for typ in ITEM_TYPES:
        block = data.get(typ) or {}
        for name in sorted(block):
            if name in seen_item_names:
                continue
            items.append(extract_item(typ, block[name]))
            seen_item_names.add(name)

    fluids: list[dict] = []
    for name in sorted(data.get("fluid", {})):
        fluids.append(extract_fluid(data["fluid"][name]))

    modules: list[dict] = []
    for name in sorted(data.get("module", {})):
        modules.append(extract_module(data["module"][name]))

    # Drop synthetic beacon-interface modules (beacon visual placeholders).
    modules = [m for m in modules if not m["name"].startswith("beacon-interface--")]

    out_files = {
        "machines.json": machines,
        "recipes.json": recipes,
        "recipe_categories.json": recipe_categories_out,
        "items.json": items,
        "fluids.json": fluids,
        "modules.json": modules,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, payload in out_files.items():
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        if isinstance(payload, list):
            print(f"wrote {path} ({len(payload)} entries)")
        else:
            print(f"wrote {path}")

    # quick verification echo
    by_name = {m["name"]: m for m in machines}
    checks = [
        ("assembling-machine-3", "crafting_speed", 1.25),
        ("foundry", "crafting_speed", 4),
        ("electromagnetic-plant", "crafting_speed", 2),
        ("recycler", "crafting_speed", 0.5),
    ]
    for n, k, expected in checks:
        m = by_name.get(n)
        actual = m and m.get(k)
        flag = "OK" if actual == expected else "MISMATCH"
        print(f"check[{flag}]: {n}.{k}={actual} (expected {expected})")

    print(f"machines={len(machines)} recipes={len(recipes)} items={len(items)} "
          f"fluids={len(fluids)} modules={len(modules)} "
          f"crafting_categories={len(cat_to_machines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
