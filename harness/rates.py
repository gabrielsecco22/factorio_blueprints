"""Harness wrapper around `tools.rate_calculator`.

Bridges a `harness.plan.ProductionPlan` to the rate engine and produces:
    - a markdown report that the orchestrator embeds in `result.report`,
    - a structured `RatesForPlan` object the synthesis pipeline can use
      to assert that throughput meets a declared target.

The wrapper is deliberately thin: planners already record `recipe`,
`machine`, and `count` per cell, so we just feed those plus any module /
beacon / research parameters that come along on the spec.

Future work: the planner can populate `cell.modules` / `cell.beacons`
once those slots exist on the dataclass; for now the wrapper accepts
empties.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from harness.plan import ProductionPlan
from harness.spec import BuildSpec
from tools.rate_calculator import (
    Beacon,
    RateInput,
    RateOutput,
    compute_rates,
)


@dataclass
class CellRate:
    """One production cell, with its computed rate output."""

    recipe: str
    machine: str
    count: int
    rates: RateOutput


@dataclass
class RatesForPlan:
    cells: list[CellRate] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def total_outputs_per_second(self) -> dict[str, float]:
        agg: dict[str, float] = {}
        for c in self.cells:
            for n, r in c.rates.outputs_per_second.items():
                agg[n] = agg.get(n, 0.0) + r
        return agg

    def total_inputs_per_second(self) -> dict[str, float]:
        agg: dict[str, float] = {}
        for c in self.cells:
            for n, r in c.rates.inputs_per_second.items():
                agg[n] = agg.get(n, 0.0) + r
        return agg

    def total_power_kw(self) -> float:
        return sum(c.rates.power_kw_total for c in self.cells)

    def output_for(self, item: str) -> float:
        return self.total_outputs_per_second().get(item, 0.0)

    def assert_meets(self, target_item: str, target_per_sec: float, tolerance: float = 1e-6) -> None:
        got = self.output_for(target_item)
        if got + tolerance < target_per_sec:
            raise AssertionError(
                f"throughput shortfall for {target_item!r}: got {got:.4f}/s, want {target_per_sec:.4f}/s"
            )

    @property
    def report(self) -> str:
        lines: list[str] = ["## Rate calculator", ""]
        for c in self.cells:
            r = c.rates
            lines.append(
                f"- **{c.count} x `{c.machine}` -> `{c.recipe}`** "
                f"({r.crafts_per_second_per_machine:.4f} crafts/s/machine, "
                f"{r.crafts_per_second_total:.4f} crafts/s total)"
            )
            if r.outputs_per_second:
                outs = ", ".join(f"{n} @ {v:.3f}/s" for n, v in sorted(r.outputs_per_second.items()))
                lines.append(f"  - outputs: {outs}")
            if r.inputs_per_second:
                ins = ", ".join(f"{n} @ {v:.3f}/s" for n, v in sorted(r.inputs_per_second.items()))
                lines.append(f"  - inputs: {ins}")
            lines.append(
                f"  - effective: speed x{r.effective_speed_multiplier:.3f}, "
                f"prod +{r.effective_productivity:.3f}, "
                f"power {r.power_kw_total:.0f} kW, "
                f"pollution {r.pollution_per_minute_total:.1f}/min"
            )
            if r.diagnostics:
                for d in r.diagnostics:
                    lines.append(f"  - warn: {d}")
        if self.diagnostics:
            lines.append("")
            lines.append("### Wrapper diagnostics")
            for d in self.diagnostics:
                lines.append(f"- {d}")
        return "\n".join(lines)


def rates_for_plan(plan: ProductionPlan, spec: Optional[BuildSpec] = None) -> RatesForPlan:
    """Compute per-cell rates for every cell in the plan.

    `spec` is consulted for module / beacon overrides and `use_modded`.
    """
    out = RatesForPlan()
    use_modded = bool(spec.use_modded) if spec is not None else False
    quality = spec.quality if spec is not None else "normal"
    research_levels = dict(spec.research_levels) if spec is not None else {}

    for cell in plan.cells:
        # Skip non-rate cells (solar panels, accumulators, etc.).
        if cell.recipe in {"solar-power", "storage"} or cell.recipe.startswith("solar"):
            continue
        try:
            modules = [(m, quality) for m in getattr(cell, "machine_modules", [])]
            beacons = [
                Beacon(
                    name=name,
                    quality=quality,
                    count=cnt,
                    modules=[(m, quality) for m in mods],
                )
                for (name, cnt, mods) in getattr(cell, "beacons", [])
            ]
            inp = RateInput(
                recipe=cell.recipe,
                machine=cell.machine,
                machine_quality=quality,
                machine_count=cell.count,
                modules=modules,
                beacons=beacons,
                use_modded=use_modded,
                research_levels=research_levels,
            )
            r = compute_rates(inp)
            out.cells.append(CellRate(recipe=cell.recipe, machine=cell.machine, count=cell.count, rates=r))
        except (KeyError, ValueError) as e:
            out.diagnostics.append(f"could not compute rates for cell {cell.recipe!r}/{cell.machine!r}: {e}")
    return out
