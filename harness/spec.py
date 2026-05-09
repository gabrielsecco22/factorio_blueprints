"""Input spec dataclasses for the harness pipeline.

A `BuildSpec` is the single point of input. The orchestrator reads it
and dispatches to a planner. Specs are intentionally permissive: any
field left at its default lets a downstream stage fill in a sensible
choice from `specs/*.json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BuildSpec:
    """Describes one production build to synthesise.

    Exactly one of (`output_rate_per_sec`, `machine_count`) must be set
    when `kind == "smelter_array"` or any throughput-driven build. For
    fixed-shape builds (`kind == "solar_field"`), neither is required;
    `machine_count` is reinterpreted as "panel count" if set.
    """

    # What kind of build to synthesise. Examples values:
    #   "smelter_array"          - one row of furnaces with input/output belts.
    #   "electric_smelter_array" - smelter_array variant with substation power.
    #   "solar_field"            - solar panels + accumulators in canonical ratio.
    #   "green_circuit_block"    - two rows: copper-cable -> electronic-circuit.
    kind: str = "smelter_array"

    # The recipe target (used by `smelter_array` etc.).
    target: Optional[str] = None

    # Throughput target (items / second). Mutually exclusive with `machine_count`.
    output_rate_per_sec: Optional[float] = None

    # Direct machine count override.
    machine_count: Optional[int] = None

    # Machine choice override. If unset, the planner picks the cheapest viable
    # machine that can craft `target`.
    machine_choice: Optional[str] = None

    # For burner machines.
    fuel: str = "coal"

    # Belt tier. Vanilla options: transport-belt, fast-transport-belt,
    # express-transport-belt, turbo-transport-belt.
    belt_tier: str = "transport-belt"

    # Inserter tier. Default plain inserter.
    inserter_tier: str = "inserter"

    # Quality tag. Vanilla = "normal" until Quality is unlocked.
    quality: str = "normal"

    # Research bonuses (for downstream throughput math).
    research_levels: dict[str, int] = field(default_factory=dict)

    # Use mod-buffed values from JSON specs instead of vanilla baselines.
    use_modded: bool = False

    # Solar-field specifics:
    solar_panel_count: Optional[int] = None  # if None, derived from accumulator_count or default.
    accumulator_count: Optional[int] = None

    # Smelter-array fuel feed (only meaningful for burner machines):
    #   None       - no fuel feed (legacy stone-smelter MVP behaviour).
    #   "shared"   - one extra burner-inserter per furnace lifts fuel from
    #                the same input belt (filtered).
    #   "separate" - a dedicated parallel fuel belt south of the input belt.
    fuel_feed: Optional[str] = None

    # Power-network choice for electric builds. Used by `electric_smelter_array`.
    # "substation" (default for that kind), "medium-electric-pole", or
    # "small-electric-pole" all work; pick whichever covers your footprint.
    pole_choice: str = "substation"

    # Green-circuit specifics:
    cable_assembler_count: Optional[int] = None
    circuit_assembler_count: Optional[int] = None

    # Beacon-smelter specifics. `beacons_per_machine` is advisory (the
    # actual count depends on layout geometry); the planner reports the
    # realised per-machine count back via `ProductionPlan.warnings`.
    # `beacon_module` and `machine_module` are item names from
    # `specs/modules.json` (e.g. "speed-module-3", "productivity-module-3");
    # leave as None to skip module insertion.
    beacons_per_machine: int = 0
    beacon_module: Optional[str] = None
    machine_module: Optional[str] = None

    # Optional human label baked into the blueprint.
    label: Optional[str] = None
