"""Planner: turn a `BuildSpec` into a `ProductionPlan`.

The plan is the pipeline's single source of truth for "what machines
make what, and how many of each". It does not care about positions or
wiring; the layout stage owns those.

Throughput math (for `smelter_array`-style builds):

    rate_per_machine = (1 + base_productivity) * crafting_speed
                       * primary_result_amount
                       / energy_required

That gives items / second per machine assuming no module slots are
populated. We deliberately ignore beacons / modules in the MVP.

`base_productivity` is read from the machine's `base_effect.productivity`
(0 for vanilla furnaces; mods add bonuses). When `use_modded` is False
we substitute the `vanilla_2_0_76.base_effect` overlay if present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from harness import catalog
from harness.spec import BuildSpec


class PlanError(ValueError):
    """Raised when a spec cannot be turned into a production plan."""


@dataclass
class ProductionCell:
    """One homogeneous batch of machines making the same recipe."""

    recipe: str
    machine: str
    count: int
    fuel: Optional[str] = None
    rate_per_machine: float = 0.0  # items per second
    rate_total: float = 0.0  # items per second
    inputs: list[tuple[str, float]] = field(default_factory=list)  # (name, items/s)
    outputs: list[tuple[str, float]] = field(default_factory=list)  # (name, items/s)
    # Modules installed in each machine of this cell (item names). When
    # non-empty, the layout stage will emit blueprint `items` requests so
    # the pasted entity arrives pre-populated.
    machine_modules: list[str] = field(default_factory=list)
    # Beacons that affect each machine of this cell. Each tuple is
    # (beacon_name, beacon_count_for_one_machine, list_of_module_names_per_beacon).
    # Only used by the rate calculator and the synthesis report; the
    # actual beacon ENTITIES are placed by the layout stage.
    beacons: list[tuple[str, int, list[str]]] = field(default_factory=list)


@dataclass
class ProductionPlan:
    """A bag of production cells plus warnings."""

    cells: list[ProductionCell] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _machine_overlay(machine: dict, use_modded: bool) -> dict:
    """Apply `vanilla_2_0_76` overlay unless `use_modded` is True."""
    if use_modded or "vanilla_2_0_76" not in machine:
        return machine
    overlaid = dict(machine)
    overlaid.update(machine["vanilla_2_0_76"])
    return overlaid


def _pick_machine_for(recipe: dict, prefer: Optional[str], use_modded: bool) -> str:
    """Pick the simplest machine that can craft `recipe`.

    Strategy: consult `recipe_categories.json` for the category, then prefer
    `prefer` if it's compatible, else pick the first listed candidate (which
    is typically the cheapest tier in our extracted JSON).
    """
    cat = recipe["category"] or "crafting"
    categories = catalog.recipe_categories()["crafting_categories"]
    candidates: list[str] = list(categories.get(cat, []))
    if not candidates:
        raise PlanError(f"no machine known for recipe category {cat!r}")
    if prefer:
        if prefer not in candidates:
            raise PlanError(
                f"machine {prefer!r} cannot craft recipe {recipe['name']!r} "
                f"(category {cat!r}); valid: {candidates}"
            )
        return prefer
    return candidates[0]


def _primary_result_amount(recipe: dict, target: str) -> float:
    for r in recipe["results"]:
        if r["name"] == target:
            return float(r["amount"])
    raise PlanError(f"recipe {recipe['name']!r} does not produce {target!r}")


def _machine_rate_per_sec(machine: dict, recipe: dict, target: str, use_modded: bool) -> float:
    overlaid = _machine_overlay(machine, use_modded)
    speed = float(overlaid["crafting_speed"])
    base_eff = overlaid.get("base_effect") or {}
    prod = float(base_eff.get("productivity", 0.0))
    energy = float(recipe["energy_required"])
    if energy <= 0:
        raise PlanError(f"recipe {recipe['name']!r} has non-positive energy_required={energy!r}")
    amount = _primary_result_amount(recipe, target)
    return (1.0 + prod) * speed * amount / energy


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def plan_smelter_array(spec: BuildSpec) -> ProductionPlan:
    if not spec.target:
        raise PlanError("smelter_array spec requires a `target` recipe name")
    recipes = catalog.recipes()
    if spec.target not in recipes:
        raise PlanError(f"unknown recipe target {spec.target!r}")
    recipe = recipes[spec.target]

    # When the kind implies a particular energy class but no machine_choice
    # was supplied, pick the simplest member of that class. Without this,
    # _pick_machine_for falls back to the first alphabetical candidate, which
    # for `smelting` is `electric-furnace` -- and the smelter_array layout
    # does not place poles, so validation later fails with
    # "12 electric entities placed but no electric poles found".
    machine_pref = spec.machine_choice
    if not machine_pref and spec.kind == "smelter_array":
        machine_pref = "stone-furnace"
    elif not machine_pref and spec.kind == "electric_smelter_array":
        machine_pref = "electric-furnace"

    machine_name = _pick_machine_for(recipe, machine_pref, spec.use_modded)
    machine = catalog.machines()[machine_name]

    rate_per_machine = _machine_rate_per_sec(machine, recipe, spec.target, spec.use_modded)

    plan = ProductionPlan()

    # Pick count.
    if spec.machine_count and spec.output_rate_per_sec:
        raise PlanError("set at most one of machine_count / output_rate_per_sec")
    if spec.machine_count is not None:
        count = spec.machine_count
    elif spec.output_rate_per_sec is not None:
        raw = spec.output_rate_per_sec / rate_per_machine
        count = int(math.ceil(raw))
        if count != raw:
            plan.warnings.append(
                f"rounded up to {count} machines for full saturation "
                f"(needed {raw:.3f} machines for {spec.output_rate_per_sec} {spec.target}/s)"
            )
    else:
        raise PlanError("smelter_array spec requires machine_count or output_rate_per_sec")

    if count <= 0:
        raise PlanError(f"resolved machine count must be positive, got {count}")

    fuel = None
    energy_source = machine.get("energy_source") or {}
    if energy_source.get("type") == "burner":
        fuel = spec.fuel
        if fuel not in catalog.items():
            raise PlanError(f"fuel item {fuel!r} not in items.json")

    # Inputs / outputs (per second, total).
    inputs: list[tuple[str, float]] = []
    for ing in recipe["ingredients"]:
        if ing.get("type", "item") != "item":
            # Skip fluid inputs in the MVP; smelter_array doesn't deal with them.
            continue
        inputs.append((ing["name"], rate_per_machine * count * float(ing["amount"])))
    outputs: list[tuple[str, float]] = []
    for r in recipe["results"]:
        if r.get("type", "item") != "item":
            continue
        outputs.append((r["name"], rate_per_machine * count * float(r["amount"])))

    cell = ProductionCell(
        recipe=spec.target,
        machine=machine_name,
        count=count,
        fuel=fuel,
        rate_per_machine=rate_per_machine,
        rate_total=rate_per_machine * count,
        inputs=inputs,
        outputs=outputs,
    )
    plan.cells.append(cell)
    return plan


def plan_solar_field(spec: BuildSpec) -> ProductionPlan:
    """Trivially turns a solar-field spec into a target-count plan.

    Solar fields are not throughput-driven (they make power, not items),
    so we skip the rate math. The layout stage uses the cell.count to
    decide how many panels and accumulators to place.
    """
    panels = spec.solar_panel_count
    accs = spec.accumulator_count

    # Default per-large-pole ratio: 24 solar panels + 20 accumulators.
    # Verified arithmetic (Nauvis): solar avg = 42 kW, day-fraction 16800/25000 = 0.672,
    # one panel produces 60 kW * 0.672 = 40.32 kW averaged but factory needs 60 kW
    # daytime; over the night fraction (5000/25000 = 0.2) accumulators hold the load.
    # The classic ratio that the wiki tabulates is 0.84 accumulators per panel.
    if panels is None and accs is None:
        panels = 24
        accs = 20
    elif panels is None:
        panels = int(math.ceil(accs / 0.84))
    elif accs is None:
        accs = int(math.ceil(panels * 0.84))

    plan = ProductionPlan()
    plan.cells.append(ProductionCell(
        recipe="solar-power",
        machine="solar-panel",
        count=panels,
    ))
    plan.cells.append(ProductionCell(
        recipe="storage",
        machine="accumulator",
        count=accs,
    ))
    return plan


def plan_green_circuit_block(spec: BuildSpec) -> ProductionPlan:
    """Two-cell plan: copper-cable assemblers feeding electronic-circuit assemblers.

    Default counts: 4 cable assemblers + 6 circuit assemblers, which gives a
    rough 2:3 ratio matching the recipe (each circuit needs 3 cable; 1 cable
    assembler outputs 2 cable per 0.5s = 4/s; 1 circuit assembler consumes
    3 cable per 0.5s / speed=0.5 = 3 cable/s; balanced ratio is 1.5:2 ~ 3:4
    cable:circuit, so 4:6 cable:circuit = 2:3 has spare cable headroom).
    """
    cable_count = spec.cable_assembler_count
    circuit_count = spec.circuit_assembler_count
    if cable_count is None and circuit_count is None:
        cable_count = 4
        circuit_count = 6
    elif cable_count is None:
        cable_count = max(1, (circuit_count * 2 + 2) // 3)
    elif circuit_count is None:
        circuit_count = max(1, (cable_count * 3 + 1) // 2)

    if cable_count <= 0 or circuit_count <= 0:
        raise PlanError("green_circuit_block needs positive assembler counts")

    recipes = catalog.recipes()
    machines = catalog.machines()
    cable_recipe = recipes["copper-cable"]
    circuit_recipe = recipes["electronic-circuit"]
    machine_name = spec.machine_choice or "assembling-machine-1"
    if machine_name not in machines:
        raise PlanError(f"unknown machine {machine_name!r}")
    machine = machines[machine_name]

    cable_rate = _machine_rate_per_sec(machine, cable_recipe, "copper-cable", spec.use_modded)
    circuit_rate = _machine_rate_per_sec(machine, circuit_recipe, "electronic-circuit", spec.use_modded)

    plan = ProductionPlan()

    plan.cells.append(ProductionCell(
        recipe="copper-cable",
        machine=machine_name,
        count=cable_count,
        rate_per_machine=cable_rate,
        rate_total=cable_rate * cable_count,
        inputs=[(ing["name"], cable_rate * cable_count * float(ing["amount"]))
                for ing in cable_recipe["ingredients"] if ing.get("type", "item") == "item"],
        outputs=[(r["name"], cable_rate * cable_count * float(r["amount"]))
                 for r in cable_recipe["results"] if r.get("type", "item") == "item"],
    ))
    plan.cells.append(ProductionCell(
        recipe="electronic-circuit",
        machine=machine_name,
        count=circuit_count,
        rate_per_machine=circuit_rate,
        rate_total=circuit_rate * circuit_count,
        inputs=[(ing["name"], circuit_rate * circuit_count * float(ing["amount"]))
                for ing in circuit_recipe["ingredients"] if ing.get("type", "item") == "item"],
        outputs=[(r["name"], circuit_rate * circuit_count * float(r["amount"]))
                 for r in circuit_recipe["results"] if r.get("type", "item") == "item"],
    ))

    # Sanity check on cable supply: cable production should meet circuit demand.
    cable_supply = cable_rate * cable_count * 2.0  # 2 cable per craft
    cable_demand = circuit_rate * circuit_count * 3.0  # 3 cable per circuit
    if cable_supply < cable_demand - 1e-6:
        plan.warnings.append(
            f"cable supply {cable_supply:.2f}/s < circuit demand {cable_demand:.2f}/s; "
            "circuits will starve"
        )

    return plan


def plan_beacon_smelter_array(spec: BuildSpec) -> ProductionPlan:
    """Beacon-boosted electric smelter array.

    Reuses `plan_smelter_array` for the base recipe / machine resolution,
    then layers on the beacon + module configuration. Throughput is
    computed via `tools.rate_calculator.compute_rates` so the planner
    matches the canonical engine math (speed floor, productivity cap,
    consumption clamp). The realised per-machine beacon count depends on
    the layout geometry (see `harness.layout.layout_beacon_smelter_array`);
    we use `spec.beacons_per_machine` here as the calibration count for
    rate maths and store it on the cell so downstream stages can adjust.
    """
    # Re-use the smelter_array path to resolve target, machine, count.
    base_plan = plan_smelter_array(spec)
    if not base_plan.cells:
        raise PlanError("beacon_smelter_array: base plan produced no cells")
    cell = base_plan.cells[0]

    # Verify the chosen machine is actually electric (beacons attach to
    # electric machines; burner furnaces have no module slots either).
    machines = catalog.machines()
    machine_proto = machines[cell.machine]
    energy_source = machine_proto.get("energy_source") or {}
    if energy_source.get("type") != "electric":
        raise PlanError(
            f"beacon_smelter_array requires an electric machine; got {cell.machine!r} "
            f"(energy_source.type={energy_source.get('type')!r})"
        )
    overlaid = _machine_overlay(machine_proto, spec.use_modded)
    machine_slots = int(overlaid.get("module_slots") or 0)

    # Build the module list for each machine (capped to its slot count).
    machine_modules: list[str] = []
    if spec.machine_module:
        if spec.machine_module not in catalog.modules():
            raise PlanError(f"unknown machine module {spec.machine_module!r}")
        machine_modules = [spec.machine_module] * machine_slots
    cell.machine_modules = machine_modules

    # Build the beacon list: one group of N identical vanilla beacons each
    # holding `bslots` copies of `spec.beacon_module`.
    beacons_per_machine = max(0, int(spec.beacons_per_machine or 0))
    beacons_list: list[tuple[str, int, list[str]]] = []
    if beacons_per_machine > 0:
        beacon_proto = catalog.beacons()["beacon"]
        if not spec.use_modded and "vanilla_2_0_76" in beacon_proto:
            bslots = int(beacon_proto["vanilla_2_0_76"].get("module_slots", 0))
        else:
            bslots = int(beacon_proto.get("module_slots", 0))
        beacon_modules: list[str] = []
        if spec.beacon_module:
            if spec.beacon_module not in catalog.modules():
                raise PlanError(f"unknown beacon module {spec.beacon_module!r}")
            beacon_modules = [spec.beacon_module] * bslots
        beacons_list = [("beacon", beacons_per_machine, beacon_modules)]
    cell.beacons = beacons_list

    # Recompute the rate via the central rate engine so the planner stays
    # in lockstep with `tools.rate_calculator`. We import lazily to avoid
    # a top-level circular import (rate_calculator -> spec is fine, but
    # plan should stay importable on its own).
    try:
        from tools.rate_calculator import (
            Beacon as _RBeacon,
            RateInput as _RInput,
            compute_rates as _compute,
        )
        modules_specs = [(m, spec.quality) for m in machine_modules]
        beacon_specs = [
            _RBeacon(
                name=name,
                quality=spec.quality,
                count=cnt,
                modules=[(m, spec.quality) for m in mods],
            )
            for (name, cnt, mods) in beacons_list
        ]
        r = _compute(_RInput(
            recipe=cell.recipe,
            machine=cell.machine,
            machine_quality=spec.quality,
            machine_count=cell.count,
            modules=modules_specs,
            beacons=beacon_specs,
            research_levels=dict(spec.research_levels),
            use_modded=spec.use_modded,
        ))
        # Use the recipe's primary-result amount * crafts/s as the per-machine
        # rate to keep continuity with `plan_smelter_array`'s convention.
        recipe = catalog.recipes()[cell.recipe]
        amt = _primary_result_amount(recipe, spec.target)
        # Productivity bonus is applied to the result in rate_calculator's
        # outputs_per_second. Recover per-machine effective rate:
        target_per_sec = r.outputs_per_second.get(spec.target, 0.0)
        per_machine = target_per_sec / max(1, cell.count)
        cell.rate_per_machine = per_machine
        cell.rate_total = target_per_sec
        # Update inputs/outputs from rate engine for accuracy.
        cell.inputs = sorted(r.inputs_per_second.items())
        cell.outputs = sorted(r.outputs_per_second.items())
        # Diagnostics from the rate engine become plan warnings.
        for d in r.diagnostics:
            base_plan.warnings.append(f"rate-calc: {d}")
    except Exception as e:  # pragma: no cover - defensive
        base_plan.warnings.append(f"could not cross-validate rates: {e}")

    return base_plan


def plan(spec: BuildSpec) -> ProductionPlan:
    """Top-level dispatch."""
    if spec.kind == "smelter_array" or spec.kind == "electric_smelter_array":
        return plan_smelter_array(spec)
    if spec.kind == "beacon_smelter_array":
        return plan_beacon_smelter_array(spec)
    if spec.kind == "solar_field":
        return plan_solar_field(spec)
    if spec.kind == "green_circuit_block":
        return plan_green_circuit_block(spec)
    raise PlanError(f"unknown spec.kind {spec.kind!r}")
