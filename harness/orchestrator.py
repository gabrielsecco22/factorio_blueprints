"""End-to-end synthesis pipeline.

Drives the stages: spec -> plan -> layout -> blueprint dict -> string,
then runs `validate.validate` against both the entity layout and the
JSON Schema. Returns a `SynthesisResult` that always contains a
blueprint string (or raises if synthesis was impossible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from harness import catalog, encode, layout, plan, validate
from harness.layout import PlacedEntity
from harness.rates import rates_for_plan
from harness.spec import BuildSpec


@dataclass
class SynthesisResult:
    blueprint_string: str
    blueprint_object: dict[str, Any]
    entity_count: int
    warnings: list[str] = field(default_factory=list)
    report: str = ""
    plan_warnings: list[str] = field(default_factory=list)


def _placed_to_blueprint_entity(ent: PlacedEntity, *, quality: Optional[str] = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "entity_number": ent.entity_number,
        "name": ent.name,
        "position": ent.position,
    }
    if ent.direction != 0:
        out["direction"] = ent.direction
    if quality and quality != "normal":
        out["quality"] = quality
    out.update(ent.extra)
    return out


def _make_icons(spec: BuildSpec, plan_obj: plan.ProductionPlan) -> list[dict[str, Any]]:
    """Pick up to four signal icons from the plan's outputs / cells."""
    icons: list[dict[str, Any]] = []
    used: set[str] = set()
    if spec.kind in ("smelter_array", "electric_smelter_array"):
        if spec.target and spec.target not in used:
            icons.append({"signal": {"type": "item", "name": spec.target}, "index": len(icons) + 1})
            used.add(spec.target)
        for cell in plan_obj.cells:
            if cell.machine not in used and len(icons) < 4:
                icons.append({"signal": {"type": "item", "name": cell.machine}, "index": len(icons) + 1})
                used.add(cell.machine)
    elif spec.kind == "solar_field":
        icons.append({"signal": {"type": "item", "name": "solar-panel"}, "index": 1})
        icons.append({"signal": {"type": "item", "name": "accumulator"}, "index": 2})
    elif spec.kind == "green_circuit_block":
        icons.append({"signal": {"type": "item", "name": "electronic-circuit"}, "index": 1})
        icons.append({"signal": {"type": "item", "name": "copper-cable"}, "index": 2})
    return icons or [{"signal": {"type": "item", "name": "blueprint"}, "index": 1}]


def _make_label(spec: BuildSpec, plan_obj: plan.ProductionPlan) -> str:
    if spec.label:
        return spec.label
    if spec.kind in ("smelter_array", "electric_smelter_array"):
        cell = plan_obj.cells[0]
        return f"{cell.count}x {cell.machine} -> {spec.target} ({cell.rate_total:.2f}/s)"
    if spec.kind == "solar_field":
        n_panels = next(c.count for c in plan_obj.cells if c.machine == "solar-panel")
        n_accs = next(c.count for c in plan_obj.cells if c.machine == "accumulator")
        return f"Solar field: {n_panels} panels + {n_accs} accumulators"
    if spec.kind == "green_circuit_block":
        n_cable = next(c.count for c in plan_obj.cells if c.recipe == "copper-cable")
        n_circuit = next(c.count for c in plan_obj.cells if c.recipe == "electronic-circuit")
        return f"Green circuit block: {n_cable} cable + {n_circuit} circuit assemblers"
    return "Synthesised blueprint"


def _make_report(
    spec: BuildSpec,
    plan_obj: plan.ProductionPlan,
    layout_obj: layout.LayoutResult,
    rates_section: str = "",
) -> str:
    lines: list[str] = []
    lines.append(f"# Synthesis report: {spec.kind}")
    lines.append("")
    lines.append("## Plan")
    for c in plan_obj.cells:
        lines.append(
            f"- {c.count} x `{c.machine}` -> `{c.recipe}` "
            f"({c.rate_per_machine:.4f} /s/machine, {c.rate_total:.4f} /s total)"
        )
        if c.fuel:
            lines.append(f"  - fuel: {c.fuel}")
        if c.inputs:
            lines.append(f"  - inputs: " + ", ".join(f"{n} @ {r:.3f}/s" for n, r in c.inputs))
        if c.outputs:
            lines.append(f"  - outputs: " + ", ".join(f"{n} @ {r:.3f}/s" for n, r in c.outputs))
    if plan_obj.warnings:
        lines.append("")
        lines.append("## Plan warnings")
        for w in plan_obj.warnings:
            lines.append(f"- {w}")
    lines.append("")
    lines.append("## Layout")
    bbox = layout_obj.bbox
    lines.append(f"- bounding box (tiles): NW=({bbox[0]},{bbox[1]}) SE=({bbox[2]},{bbox[3]})")
    lines.append(f"- entity count: {len(layout_obj.entities)}")
    counts: dict[str, int] = {}
    for e in layout_obj.entities:
        counts[e.name] = counts.get(e.name, 0) + 1
    lines.append("- breakdown:")
    for name, n in sorted(counts.items()):
        lines.append(f"  - {name}: {n}")
    if layout_obj.warnings:
        lines.append("")
        lines.append("## Layout warnings")
        for w in layout_obj.warnings:
            lines.append(f"- {w}")
    if rates_section:
        lines.append("")
        lines.append(rates_section)
    return "\n".join(lines)


def synthesize(spec: BuildSpec) -> SynthesisResult:
    """Drive the spec -> blueprint pipeline end-to-end."""
    plan_obj = plan.plan(spec)
    layout_obj = layout.layout(plan_obj, spec)

    # Rate-calc pass (best effort: never fail synthesis on a rate hiccup).
    try:
        rates = rates_for_plan(plan_obj, spec)
        rates_md = rates.report
        # Optional shortfall assertion when caller specified a target rate.
        if (
            getattr(spec, "output_rate_per_sec", None) is not None
            and spec.target is not None
        ):
            try:
                rates.assert_meets(spec.target, float(spec.output_rate_per_sec), tolerance=1e-3)
            except AssertionError as e:
                rates_md += f"\n\n**SHORTFALL**: {e}"
    except Exception as e:  # pragma: no cover - defensive
        rates_md = f"## Rate calculator\n\n(skipped: {e})"

    # Build the blueprint JSON object.
    bp_entities = [
        _placed_to_blueprint_entity(e, quality=spec.quality)
        for e in layout_obj.entities
    ]
    blueprint_obj: dict[str, Any] = {
        "blueprint": {
            "item": "blueprint",
            "label": _make_label(spec, plan_obj),
            "icons": _make_icons(spec, plan_obj),
            "entities": bp_entities,
            "version": encode.PACKED_VERSION_2_0_76,
        }
    }

    # Validate.
    report = validate.validate(layout_obj, blueprint_obj)
    if report.errors:
        details = "\n".join(report.errors)
        raise ValueError(f"validation failed for {spec.kind!r}:\n{details}")

    bp_string = encode.encode(blueprint_obj)

    # Round-trip check.
    decoded = encode.decode(bp_string)
    if decoded != blueprint_obj:
        raise ValueError(
            f"round-trip failed: decoded blueprint differs from source for {spec.kind!r}"
        )

    return SynthesisResult(
        blueprint_string=bp_string,
        blueprint_object=blueprint_obj,
        entity_count=len(bp_entities),
        warnings=plan_obj.warnings + layout_obj.warnings + report.warnings,
        report=_make_report(spec, plan_obj, layout_obj, rates_section=rates_md),
        plan_warnings=plan_obj.warnings,
    )
