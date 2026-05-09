"""Command-line interface to `tools/rate_calculator`.

Subcommands
-----------

    compute        Compute throughput / power / pollution for one config.
    belt-saturate  Show how many belts a recipe-target rate saturates.
    compare        Side-by-side compare a recipe across multiple machines.

Examples
--------

    python3 tools/rate_cli.py compute \\
        --recipe electronic-circuit --machine assembling-machine-3 \\
        --modules prod-3,prod-3,prod-3,prod-3 \\
        --beacons "beacon:speed-3,speed-3" --count 10

    python3 tools/rate_cli.py belt-saturate \\
        --recipe iron-plate --machine steel-furnace --count 24 \\
        --belt-tier transport-belt

    python3 tools/rate_cli.py compare --recipe iron-plate \\
        --machine stone-furnace --machine steel-furnace --machine electric-furnace
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.rate_calculator import (
    Beacon,
    RateInput,
    RateOutput,
    belt_saturation,
    compute_rates,
    machines_catalog,
    modules_catalog,
)

# ---------------------------------------------------------------------------
# Module shorthand
# ---------------------------------------------------------------------------

MODULE_SHORTHANDS = {
    "speed-1": "speed-module",
    "speed-2": "speed-module-2",
    "speed-3": "speed-module-3",
    "prod-1": "productivity-module",
    "prod-2": "productivity-module-2",
    "prod-3": "productivity-module-3",
    "eff-1": "efficiency-module",
    "eff-2": "efficiency-module-2",
    "eff-3": "efficiency-module-3",
    "qual-1": "quality-module",
    "qual-2": "quality-module-2",
    "qual-3": "quality-module-3",
}


def _resolve_module(name: str) -> str:
    if name in MODULE_SHORTHANDS:
        return MODULE_SHORTHANDS[name]
    if name in modules_catalog():
        return name
    raise SystemExit(f"unknown module {name!r}; known shorthands: {sorted(MODULE_SHORTHANDS)}")


def _parse_modules(spec: Optional[str], default_quality: str = "normal") -> list[tuple[str, str]]:
    """Parse 'prod-3,prod-3' or 'prod-3@legendary,speed-3@rare'."""
    if not spec:
        return []
    out: list[tuple[str, str]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "@" in part:
            name, q = part.split("@", 1)
        else:
            name, q = part, default_quality
        out.append((_resolve_module(name), q))
    return out


def _parse_beacons(specs: list[str], default_quality: str = "normal") -> list[Beacon]:
    """Parse '--beacons "beacon:speed-3,speed-3" --beacons "beacon:speed-3,speed-3"'.

    Optional count suffix: 'beacon*12:speed-3,speed-3'.
    Optional quality suffix: 'beacon@rare:speed-3@legendary'.
    """
    out: list[Beacon] = []
    for s in specs or []:
        head, _, mods = s.partition(":")
        # head is "name[*count][@quality]"
        count = 1
        quality = default_quality
        if "*" in head:
            name, c = head.split("*", 1)
            count = int(c.split("@", 1)[0])
            if "@" in c:
                quality = c.split("@", 1)[1]
        else:
            name = head
        if "@" in name:
            name, quality = name.split("@", 1)
        bmods = _parse_modules(mods, quality)
        out.append(Beacon(name=name, quality=quality, count=count, modules=bmods))
    return out


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------


def _fmt_rate(r: float) -> str:
    if r == 0:
        return "0"
    if r >= 100:
        return f"{r:.1f}/s"
    if r >= 1:
        return f"{r:.3f}/s"
    return f"{r:.4f}/s"


def _print_table(rows: list[list[str]]) -> None:
    if not rows:
        return
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    sep = "  "
    for i, row in enumerate(rows):
        line = sep.join(cell.ljust(widths[j]) for j, cell in enumerate(row))
        print(line)
        if i == 0:
            print(sep.join("-" * w for w in widths))


def _format_compute_report(out: RateOutput) -> str:
    lines: list[str] = []
    lines.append(
        f"## Rate report: {out.machine_count}x {out.machine}"
        f" -> {out.recipe} (machine quality: {out.machine_quality})"
    )
    lines.append("")
    lines.append("### Effective modifiers")
    rows: list[list[str]] = [
        ["effect", "raw bonus", "effective"],
        ["speed", f"{out.raw_speed_bonus:+.3f}", f"x{out.effective_speed_multiplier:.3f}"],
        ["productivity", f"{out.raw_productivity_bonus:+.3f}", f"+{out.effective_productivity:.3f}"],
        ["consumption", f"{out.raw_consumption_bonus:+.3f}", f"x{out.effective_consumption_multiplier:.3f}"],
        ["pollution", f"{out.raw_pollution_bonus:+.3f}", f"x{out.effective_pollution_multiplier:.3f}"],
        ["quality cascade", f"{out.raw_quality_bonus:+.3f}", f"{out.effective_quality_chance:.4f}/craft"],
    ]
    _print_table(rows)
    lines.append("")
    print()
    print("### Throughput")
    print(
        f"  crafts/s/machine: {out.crafts_per_second_per_machine:.4f}   "
        f"crafts/s total: {out.crafts_per_second_total:.4f}"
    )
    print()
    print("### Inputs (per second, total)")
    rows = [["item", "rate"]]
    for n, r in sorted(out.inputs_per_second.items()):
        rows.append([n, _fmt_rate(r)])
    _print_table(rows)
    print()
    print("### Outputs (per second, total)")
    rows = [["item", "rate"]]
    for n, r in sorted(out.outputs_per_second.items()):
        rows.append([n, _fmt_rate(r)])
    _print_table(rows)
    if any(len(qm) > 1 for qm in out.outputs_by_quality_per_second.values()):
        print()
        print("### Quality cascade (per second, total)")
        rows = [["item", "quality", "rate"]]
        for n, qm in sorted(out.outputs_by_quality_per_second.items()):
            for q, r in sorted(qm.items()):
                if r > 0:
                    rows.append([n, q, _fmt_rate(r)])
        _print_table(rows)
    print()
    print("### Power and pollution")
    print(f"  machine: {out.power_kw_per_machine:.1f} kW each   total: {out.power_kw_total:.1f} kW")
    print(f"  beacon power: {out.beacon_power_kw_total:.1f} kW")
    print(
        f"  pollution: {out.pollution_per_minute_per_machine:.2f}/min/machine, "
        f"{out.pollution_per_minute_total:.2f}/min total"
    )
    if out.diagnostics:
        print()
        print("### Diagnostics")
        for d in out.diagnostics:
            print(f"  - {d}")
    return ""


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_compute(args: argparse.Namespace) -> int:
    inp = RateInput(
        recipe=args.recipe,
        machine=args.machine,
        machine_quality=args.machine_quality,
        modules=_parse_modules(args.modules, args.module_quality),
        beacons=_parse_beacons(args.beacons or [], args.beacon_quality),
        machine_count=args.count,
        use_modded=args.use_modded,
    )
    if args.research_recipe_prod:
        inp.research_levels["change-recipe-productivity"] = {
            args.recipe: int(args.research_recipe_prod)
        }
    out = compute_rates(inp)
    _format_compute_report(out)
    return 0


def cmd_belt_saturate(args: argparse.Namespace) -> int:
    inp = RateInput(
        recipe=args.recipe,
        machine=args.machine,
        machine_quality=args.machine_quality,
        modules=_parse_modules(args.modules, args.module_quality),
        beacons=_parse_beacons(args.beacons or [], args.beacon_quality),
        machine_count=args.count,
        use_modded=args.use_modded,
    )
    out = compute_rates(inp)
    print(f"## Belt saturation report")
    print(f"  recipe   : {args.recipe}")
    print(f"  machine  : {args.count} x {args.machine}")
    print(f"  belt tier: {args.belt_tier}")
    print()
    rows = [["item", "items/s", "belts (full)", "lanes"]]
    for n, r in sorted(out.outputs_per_second.items()):
        sat = belt_saturation(r, args.belt_tier)
        rows.append([n, _fmt_rate(r), f"{sat['belt_full_belts']:.3f}", f"{sat['belt_lanes']:.3f}"])
    _print_table(rows)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    rows: list[list[str]] = [
        ["machine", "crafts/s", "out (primary)", "power kW", "pollution/min", "diagnostics"]
    ]
    for m_name in args.machine:
        try:
            inp = RateInput(
                recipe=args.recipe,
                machine=m_name,
                use_modded=args.use_modded,
                modules=_parse_modules(args.modules),
            )
            out = compute_rates(inp)
        except Exception as e:
            rows.append([m_name, "ERR", "-", "-", "-", str(e)])
            continue
        # primary output: first recipe result
        primary = next(iter(out.outputs_per_second.items()), ("-", 0.0))
        rows.append(
            [
                m_name,
                f"{out.crafts_per_second_per_machine:.4f}",
                f"{primary[0]} {_fmt_rate(primary[1])}",
                f"{out.power_kw_per_machine:.1f}",
                f"{out.pollution_per_minute_per_machine:.2f}",
                "; ".join(out.diagnostics)[:60],
            ]
        )
    _print_table(rows)
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--recipe", required=True, help="recipe internal name (e.g. iron-plate)")
    p.add_argument("--modules", default="", help="comma-separated module list (e.g. prod-3,prod-3)")
    p.add_argument("--module-quality", default="normal", help="default module quality")
    p.add_argument("--beacons", action="append", default=[], help='beacon spec, e.g. "beacon*8:speed-3,speed-3"')
    p.add_argument("--beacon-quality", default="normal", help="default beacon quality")
    p.add_argument("--machine-quality", default="normal", help="machine quality tier")
    p.add_argument("--count", type=int, default=1, help="machine count")
    p.add_argument(
        "--use-modded",
        action="store_true",
        default=False,
        help="use modded values from JSON (default: vanilla baseline)",
    )
    p.add_argument(
        "--research-recipe-prod",
        type=int,
        default=0,
        help="level of change-recipe-productivity tech for THIS recipe",
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rate_cli", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("compute", help="full rate report for one config")
    _add_common_args(pc)
    pc.add_argument("--machine", required=True, help="machine name")
    pc.set_defaults(func=cmd_compute)

    pb = sub.add_parser("belt-saturate", help="how many belts saturated by output")
    _add_common_args(pb)
    pb.add_argument("--machine", required=True, help="machine name")
    pb.add_argument("--belt-tier", default="transport-belt", help="belt prototype name")
    pb.set_defaults(func=cmd_belt_saturate)

    pcmp = sub.add_parser("compare", help="compare a recipe across multiple machines")
    pcmp.add_argument("--recipe", required=True)
    pcmp.add_argument("--machine", action="append", required=True, help="repeatable")
    pcmp.add_argument("--modules", default="")
    pcmp.add_argument("--use-modded", action="store_true", default=False)
    pcmp.set_defaults(func=cmd_compare)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
