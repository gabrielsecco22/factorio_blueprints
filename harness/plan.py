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

    machine_name = _pick_machine_for(recipe, spec.machine_choice, spec.use_modded)
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


def plan(spec: BuildSpec) -> ProductionPlan:
    """Top-level dispatch."""
    if spec.kind == "smelter_array":
        return plan_smelter_array(spec)
    if spec.kind == "solar_field":
        return plan_solar_field(spec)
    raise PlanError(f"unknown spec.kind {spec.kind!r}")
