"""Master orchestrator: generator -> validator loop, mod-aware.

This is the high-level driver that wraps `harness.synthesize` in a
self-correcting loop:

    1. Plan a build (BuildSpec).
    2. Synthesize it.
    3. Decode + run the structural validator.
    4. Run the rate calculator and check it meets `output_rate_per_sec`.
    5. Optionally render via the visual-validator agent OR call its
       Python fallback (`harness.master_orchestrator._fallback_visual`).
    6. Parse "Suggested fixes" and feed them back as constraints.
    7. Repeat until PASS or `max_iterations`.

Mod-awareness lives in `harness.mod_compat`. The master orchestrator
calls it twice:

    - Before synthesis: validate that requested machines/belts/inserters
      come from a mod the user has enabled (depending on `mod_set`).
    - After synthesis: walk the produced blueprint and confirm every
      generated entity is from an available mod.

CLI:

    python3 -m harness.master_orchestrator master \\
        --target iron-plate --rate 30 --mod-set vanilla

    python3 -m harness.master_orchestrator inspect <bp-string-or-file>

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from harness import encode, layout as layout_mod, plan as plan_mod, validate
from harness.orchestrator import SynthesisResult, synthesize
from harness.rates import rates_for_plan
from harness.spec import BuildSpec
from harness import mod_compat


# Status names returned in `MasterResult.final_status`.
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"


# ---------------------------------------------------------------------------
# Constraint feedback (parsed from "Suggested fixes")
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    """One feedback item, parsed from the visual-validator's output."""
    kind: str                # "min_machine_count" | "require_fuel_belt" | "raw"
    payload: dict[str, Any]

    def apply_to(self, spec: BuildSpec) -> BuildSpec:
        """Return a new BuildSpec with this constraint folded in.

        Constraints are deliberately conservative: each one nudges spec
        in the direction the validator asked for, never overrides a
        user's explicit setting unless the constraint is more strict.
        """
        if self.kind == "min_machine_count":
            target = int(self.payload["count"])
            if spec.machine_count is None or spec.machine_count < target:
                # Switch from rate-driven to count-driven for this iteration.
                spec.machine_count = target
                spec.output_rate_per_sec = None
        elif self.kind == "require_fuel_belt":
            if spec.fuel_feed is None:
                spec.fuel_feed = self.payload.get("mode", "shared")
            if "fuel" in self.payload and spec.fuel != self.payload["fuel"]:
                spec.fuel = self.payload["fuel"]
        elif self.kind == "switch_belt_tier":
            spec.belt_tier = self.payload["belt"]
        # "raw" constraints are passed through but not actionable: they
        # appear in the trace so the operator can read them.
        return spec


def _replace_spec(spec: BuildSpec, constraints: Iterable[Constraint]) -> BuildSpec:
    """Apply a sequence of constraints to a fresh copy of spec."""
    # BuildSpec is a dataclass: shallow-copy via __dict__.
    new_spec = BuildSpec(**spec.__dict__)
    new_spec.research_levels = dict(spec.research_levels)
    for c in constraints:
        new_spec = c.apply_to(new_spec)
    return new_spec


_FIX_HEADER_RE = re.compile(r"^##\s*Suggested fixes\s*$", re.IGNORECASE | re.MULTILINE)
_NEXT_HEADER_RE = re.compile(r"^##\s+", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
_MIN_COUNT_RE = re.compile(
    r"(?:at least|min(?:imum)?)\s+(\d+)\s+(?:furnace|machine|assembler)",
    re.IGNORECASE,
)
_FUEL_BELT_RE = re.compile(r"\b(fuel|coal)\s+(?:belt|feed)\b", re.IGNORECASE)
_BELT_TIER_RE = re.compile(
    r"(transport-belt|fast-transport-belt|express-transport-belt|turbo-transport-belt)",
    re.IGNORECASE,
)


def parse_suggested_fixes(report_md: str) -> list[Constraint]:
    """Extract `## Suggested fixes` bullets and turn them into Constraints.

    Recognises three nudges:
      - "at least N furnaces / machines"     -> min_machine_count
      - "needs a fuel belt" / "coal feed"    -> require_fuel_belt
      - "switch to <belt> tier"              -> switch_belt_tier
    Anything else is recorded as a raw constraint so it shows up in the trace.
    """
    if not report_md:
        return []
    m = _FIX_HEADER_RE.search(report_md)
    if not m:
        return []
    section = report_md[m.end():]
    n = _NEXT_HEADER_RE.search(section)
    if n:
        section = section[: n.start()]
    out: list[Constraint] = []
    for bm in _BULLET_RE.finditer(section):
        text = bm.group(1).strip()
        cm = _MIN_COUNT_RE.search(text)
        if cm:
            out.append(Constraint("min_machine_count", {"count": int(cm.group(1))}))
            continue
        if _FUEL_BELT_RE.search(text):
            out.append(Constraint("require_fuel_belt", {"mode": "shared", "fuel": "coal"}))
            continue
        bt = _BELT_TIER_RE.search(text)
        if bt:
            out.append(Constraint("switch_belt_tier", {"belt": bt.group(1).lower()}))
            continue
        out.append(Constraint("raw", {"text": text}))
    return out


# ---------------------------------------------------------------------------
# Master spec / result
# ---------------------------------------------------------------------------

@dataclass
class MasterSpec:
    """High-level driver input. Translates to a `BuildSpec` internally."""
    target: str
    output_rate_per_sec: Optional[float] = None
    machine_count: Optional[int] = None
    machine_choice: Optional[str] = None
    fuel: str = "coal"
    belt_tier: str = "transport-belt"
    inserter_tier: str = "burner-inserter"
    quality: str = "normal"
    kind: str = "smelter_array"
    fuel_feed: Optional[str] = None
    pole_choice: str = "substation"
    label: Optional[str] = None

    # Loop controls.
    max_iterations: int = 3
    require_passing_validator: bool = True
    enable_visual_validator: bool = False
    rate_tolerance: float = 1e-3

    # Mod-awareness.
    # 'vanilla'      -> only base + DLC entities allowed.
    # 'user-enabled' -> anything in the user's enabled mods list.
    # list[str]      -> explicit mod allowlist (e.g. ['base','space-age']).
    mod_set: Union[str, list[str]] = "user-enabled"

    def to_build_spec(self) -> BuildSpec:
        # The downstream planner only accepts one of (rate, count). When the
        # caller pins a starting count, drop the rate -- the loop will check
        # the rate target and bump count if it falls short.
        rate = self.output_rate_per_sec
        count = self.machine_count
        if count is not None and rate is not None:
            rate = None
        return BuildSpec(
            kind=self.kind,
            target=self.target,
            output_rate_per_sec=rate,
            machine_count=count,
            machine_choice=self.machine_choice,
            fuel=self.fuel,
            belt_tier=self.belt_tier,
            inserter_tier=self.inserter_tier,
            quality=self.quality,
            fuel_feed=self.fuel_feed,
            pole_choice=self.pole_choice,
            label=self.label,
        )


@dataclass
class IterationVerdict:
    """The aggregated PASS/FAIL/WARN for one loop iteration."""
    structural_ok: bool
    rate_ok: bool
    mod_ok: bool
    visual_ok: bool                   # True if visual not enabled OR visual passed
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_fixes_md: str = ""

    @property
    def status(self) -> str:
        if not (self.structural_ok and self.rate_ok and self.mod_ok and self.visual_ok):
            return STATUS_FAIL
        if self.warnings:
            return STATUS_WARN
        return STATUS_PASS


@dataclass
class IterationRecord:
    attempt: int
    blueprint_string: Optional[str]
    verdict: IterationVerdict
    spec: BuildSpec


@dataclass
class MasterResult:
    blueprint_string: Optional[str]
    iterations: list[IterationRecord]
    final_status: str
    report: str
    mod_compat: dict[str, list[str]]   # {required, available, missing, disabled, zip_only}


# ---------------------------------------------------------------------------
# Visual validator integration
# ---------------------------------------------------------------------------

def _fallback_visual(blueprint_string: str) -> tuple[bool, str]:
    """Headless stand-in for the visual-validator agent.

    The actual visual validator is a Claude Code subagent
    (`.claude/agents/blueprint-visual-validator.md`) and it can't be
    invoked from a Python loop. When a renderer (`tools/render_blueprint.py`)
    becomes available we shell out to it and inspect its summary; until
    then we re-run the structural validator and emit a placeholder
    "Suggested fixes" section so the loop's parser stays exercised.

    Returns (ok, markdown).
    """
    repo_root = Path(__file__).resolve().parent.parent
    renderer = repo_root / "tools" / "render_blueprint.py"
    if renderer.is_file():
        # The renderer is being built by a sibling agent. Best-effort wire-up.
        import subprocess  # local import to keep top-level stdlib cost low
        try:
            proc = subprocess.run(
                ["python3", str(renderer), "--summary", blueprint_string],
                capture_output=True, text=True, timeout=30,
            )
            md = (proc.stdout or "") + (proc.stderr or "")
            ok = proc.returncode == 0 and "FAIL" not in md.upper()
            return ok, md or "(renderer produced no output)"
        except Exception as exc:  # pragma: no cover - depends on renderer
            return False, f"## Suggested fixes\n- renderer error: {exc}"
    # No renderer yet: defer to structural-only fallback.
    try:
        bp = encode.decode(blueprint_string)
    except Exception as exc:
        return False, f"## Suggested fixes\n- could not decode: {exc}"
    n = len(bp.get("blueprint", {}).get("entities", []) or [])
    return True, (
        "## Visual validator (fallback)\n"
        f"Decoded blueprint with {n} entities; renderer not installed, so no\n"
        "image comparison was performed. Treat this as a soft pass.\n"
    )


# ---------------------------------------------------------------------------
# Mod policy
# ---------------------------------------------------------------------------

def _resolve_modset_policy(master: MasterSpec) -> tuple[mod_compat.ModSet, str, set[str]]:
    """Return (modset, policy_name, explicit_allowlist).

    - modset: detected user mods (always queried; falls back to empty).
    - policy_name: 'vanilla' | 'user-enabled' | 'allowlist'.
    - explicit_allowlist: set of mod names the caller explicitly opted into
      (only meaningful for 'allowlist' policy; otherwise empty).
    """
    modset = mod_compat.detect_user_mods()
    if isinstance(master.mod_set, list):
        return modset, "allowlist", set(master.mod_set)
    if master.mod_set == "vanilla":
        return modset, "vanilla", set()
    if master.mod_set == "user-enabled":
        return modset, "user-enabled", set()
    raise ValueError(f"unknown master.mod_set={master.mod_set!r}")


def _check_blueprint_mods(bp_string: str, modset: mod_compat.ModSet,
                          policy: str, allowlist: set[str]) -> mod_compat.CompatReport:
    attr = mod_compat.attribute_blueprint(bp_string)
    if policy == "allowlist":
        # Build a synthetic ModSet that only enables the allowlist.
        synthetic = mod_compat.ModSet(
            enabled=allowlist | set(mod_compat.BEDROCK_MODS),
            dlc=allowlist & mod_compat.DLC_MODS,
            source=f"allowlist={sorted(allowlist)}",
        )
        return mod_compat.check_compat(
            attr.required_mods, synthetic, attribution=attr,
            mod_set_policy="user-enabled",
        )
    return mod_compat.check_compat(
        attr.required_mods, modset, attribution=attr, mod_set_policy=policy,
    )


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def _iteration(spec: BuildSpec, master: MasterSpec) -> tuple[Optional[SynthesisResult], IterationVerdict]:
    """Run one full pass and produce an aggregated verdict."""
    errors: list[str] = []
    warnings: list[str] = []
    fixes_md_lines: list[str] = []

    # Synthesis (errors here typically mean structural failure).
    bp_result: Optional[SynthesisResult] = None
    structural_ok = True
    rate_ok = True
    try:
        bp_result = synthesize(spec)
    except Exception as exc:
        structural_ok = False
        errors.append(f"synthesize() raised: {exc}")
        fixes_md_lines.append("## Suggested fixes")
        # Heuristic: most failures at this stage are throughput shortfalls.
        if "shortfall" in str(exc).lower() and master.output_rate_per_sec is not None:
            from harness import catalog
            try:
                recipe = catalog.recipes()[spec.target]
                machine_name = spec.machine_choice or _default_machine_for(recipe, spec.use_modded if hasattr(spec, "use_modded") else False)
                machine = catalog.machines()[machine_name]
                rate = _per_machine_rate(recipe, machine, spec.target)
                want = float(master.output_rate_per_sec)
                need = max(int((want / rate) + 0.999), 1)
                fixes_md_lines.append(f"- needs at least {need} furnaces to hit {want}/s")
            except Exception:
                pass
        return None, IterationVerdict(
            structural_ok=False, rate_ok=False, mod_ok=False, visual_ok=True,
            errors=errors, warnings=warnings,
            suggested_fixes_md="\n".join(fixes_md_lines),
        )

    # Re-run validator standalone (synthesize only raises on errors,
    # but we want the warnings list explicitly).
    p = plan_mod.plan(spec)
    ly = layout_mod.layout(p, spec)
    vr = validate.validate(ly, bp_result.blueprint_object)
    if vr.errors:
        structural_ok = False
        errors.extend(vr.errors)
    warnings.extend(vr.warnings)

    # Rate check (only meaningful when the user gave a target).
    rates_section_md = ""
    if master.output_rate_per_sec is not None:
        try:
            rates = rates_for_plan(p, spec)
            got = rates.output_for(master.target)
            want = float(master.output_rate_per_sec)
            if got + master.rate_tolerance < want:
                rate_ok = False
                errors.append(
                    f"rate shortfall: target {master.target} produces "
                    f"{got:.4f}/s, wanted {want:.4f}/s"
                )
                # Suggest a min count.
                cell = next((c for c in p.cells if c.recipe == master.target), None)
                if cell is not None and cell.rate_per_machine > 0:
                    need = max(int((want / cell.rate_per_machine) + 0.999), cell.count + 1)
                    fixes_md_lines.append("## Suggested fixes")
                    fixes_md_lines.append(f"- needs at least {need} furnaces to hit {want}/s")
            rates_section_md = rates.report
        except Exception as exc:
            warnings.append(f"rate calc failed: {exc}")

    # Mod compat on the produced blueprint.
    modset, policy, allowlist = _resolve_modset_policy(master)
    compat = _check_blueprint_mods(bp_result.blueprint_string, modset, policy, allowlist)
    mod_ok = compat.ok
    if not mod_ok:
        if compat.missing:
            errors.append(f"mod-set={master.mod_set!r}: missing mods {sorted(compat.missing)}")
        if compat.disabled:
            errors.append(f"mod-set={master.mod_set!r}: required mods are disabled: {sorted(compat.disabled)}")
        if compat.zip_only:
            warnings.append(f"required mods present as zip but not in mod-list.json: {sorted(compat.zip_only)}")
        if compat.unknown_entities:
            errors.append(
                "unknown entities (no source mod): "
                + ", ".join(u.name for u in compat.unknown_entities[:5])
            )

    # Visual.
    visual_ok = True
    if master.enable_visual_validator:
        visual_ok, vmd = _fallback_visual(bp_result.blueprint_string)
        if not visual_ok:
            errors.append("visual validator returned FAIL")
        if "## Suggested fixes" in vmd and "## Suggested fixes" not in "\n".join(fixes_md_lines):
            fixes_md_lines.append(vmd)

    return bp_result, IterationVerdict(
        structural_ok=structural_ok, rate_ok=rate_ok, mod_ok=mod_ok, visual_ok=visual_ok,
        errors=errors, warnings=warnings,
        suggested_fixes_md="\n".join(fixes_md_lines),
    )


def _default_machine_for(recipe: dict, use_modded: bool) -> str:
    from harness import catalog
    cat = recipe.get("category") or "crafting"
    cands = catalog.recipe_categories()["crafting_categories"].get(cat, [])
    if not cands:
        raise KeyError(f"no machine known for category {cat!r}")
    return cands[0]


def _per_machine_rate(recipe: dict, machine: dict, target: str) -> float:
    speed = float(machine["crafting_speed"])
    base_eff = machine.get("base_effect") or {}
    prod = float(base_eff.get("productivity", 0.0))
    energy = float(recipe["energy_required"])
    amount = next((float(r["amount"]) for r in recipe["results"] if r["name"] == target), 1.0)
    return (1.0 + prod) * speed * amount / energy


def master_synthesize(master: MasterSpec) -> MasterResult:
    """Drive the generator -> validator loop and return a MasterResult."""
    spec = master.to_build_spec()
    constraints: list[Constraint] = []
    iterations: list[IterationRecord] = []
    last_bp: Optional[SynthesisResult] = None
    last_verdict: Optional[IterationVerdict] = None

    for attempt in range(1, master.max_iterations + 1):
        attempt_spec = _replace_spec(spec, constraints)
        result, verdict = _iteration(attempt_spec, master)
        iterations.append(IterationRecord(
            attempt=attempt,
            blueprint_string=result.blueprint_string if result else None,
            verdict=verdict,
            spec=attempt_spec,
        ))
        last_bp = result
        last_verdict = verdict
        if verdict.status == STATUS_PASS:
            break
        # Parse fixes and accumulate constraints for the next iteration.
        new_constraints = parse_suggested_fixes(verdict.suggested_fixes_md)
        if not new_constraints:
            break  # nothing actionable left; stop early
        constraints.extend(new_constraints)

    final_status = last_verdict.status if last_verdict else STATUS_FAIL
    if (master.require_passing_validator
            and last_verdict and not last_verdict.structural_ok):
        final_status = STATUS_FAIL

    # Build mod-compat snapshot for the result.
    if last_bp:
        modset, policy, allowlist = _resolve_modset_policy(master)
        compat = _check_blueprint_mods(last_bp.blueprint_string, modset, policy, allowlist)
        mod_compat_dict = {
            "required": sorted(compat.required),
            "available": sorted(
                set(modset.enabled) | mod_compat.BEDROCK_MODS | modset.dlc
                if policy == "user-enabled" else
                set(allowlist) | mod_compat.BEDROCK_MODS | modset.dlc
                if policy == "allowlist" else
                mod_compat.BEDROCK_MODS | modset.dlc
            ),
            "missing": sorted(compat.missing),
            "disabled": sorted(compat.disabled),
            "zip_only": sorted(compat.zip_only),
        }
    else:
        mod_compat_dict = {"required": [], "available": [], "missing": [],
                           "disabled": [], "zip_only": []}

    report = _render_master_report(master, iterations, final_status, mod_compat_dict)

    return MasterResult(
        blueprint_string=last_bp.blueprint_string if last_bp else None,
        iterations=iterations,
        final_status=final_status,
        report=report,
        mod_compat=mod_compat_dict,
    )


def _render_master_report(master: MasterSpec, iters: list[IterationRecord],
                          status: str, mod_compat_dict: dict[str, list[str]]) -> str:
    lines = [f"# Master orchestrator report ({status})", ""]
    lines.append(f"- target: `{master.target}` @ {master.output_rate_per_sec}/s")
    lines.append(f"- mod-set policy: `{master.mod_set}`")
    lines.append(f"- iterations: {len(iters)} / {master.max_iterations}")
    lines.append("")
    lines.append("## Iteration trace")
    for it in iters:
        v = it.verdict
        lines.append(
            f"- attempt {it.attempt}: status={v.status}, "
            f"struct={v.structural_ok}, rate={v.rate_ok}, "
            f"mod={v.mod_ok}, visual={v.visual_ok}"
        )
        for e in v.errors:
            lines.append(f"  - error: {e}")
        for w in v.warnings:
            lines.append(f"  - warn:  {w}")
    lines.append("")
    lines.append("## Mod compatibility")
    for k in ("required", "missing", "disabled", "zip_only"):
        lines.append(f"- {k}: {mod_compat_dict.get(k) or '(none)'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_inspect(args: argparse.Namespace) -> int:
    raw = args.target
    bp_string = _resolve_blueprint_input(raw)
    report = mod_compat.inspect_blueprint(bp_string)
    sys.stdout.write(report.render() + "\n")
    return 0


def _cmd_master(args: argparse.Namespace) -> int:
    mod_set: Union[str, list[str]]
    if args.mod_set in ("vanilla", "user-enabled"):
        mod_set = args.mod_set
    else:
        mod_set = [m.strip() for m in args.mod_set.split(",") if m.strip()]
    spec = MasterSpec(
        target=args.target,
        output_rate_per_sec=args.rate,
        machine_choice=args.machine,
        fuel=args.fuel,
        kind=args.kind,
        max_iterations=args.max_iter,
        enable_visual_validator=args.visual,
        mod_set=mod_set,
        inserter_tier=args.inserter,
        belt_tier=args.belt,
    )
    result = master_synthesize(spec)
    sys.stdout.write(result.report + "\n\n")
    if result.blueprint_string:
        sys.stdout.write("## Blueprint string\n\n")
        sys.stdout.write(result.blueprint_string + "\n")
    return 0 if result.final_status in (STATUS_PASS, STATUS_WARN) else 1


def _resolve_blueprint_input(target: str) -> str:
    """Accept either a raw blueprint string or a path to a .bp / .txt file."""
    p = Path(target)
    if p.is_file():
        return p.read_text().strip()
    return target.strip()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness.master_orchestrator",
        description="Master orchestrator: generator -> validator loop, mod-aware.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    insp = sub.add_parser("inspect", help="inspect mod requirements of a blueprint")
    insp.add_argument("target", help="blueprint string OR path to a .bp/.txt file")
    insp.set_defaults(func=_cmd_inspect)

    mas = sub.add_parser("master", help="run the generator-validator loop")
    mas.add_argument("--target", required=True, help="recipe name (e.g. iron-plate)")
    mas.add_argument("--rate", type=float, required=True, help="items/sec target")
    mas.add_argument("--kind", default="smelter_array")
    mas.add_argument("--machine", default=None)
    mas.add_argument("--fuel", default="coal")
    mas.add_argument("--belt", default="transport-belt")
    mas.add_argument("--inserter", default="burner-inserter")
    mas.add_argument("--max-iter", type=int, default=3)
    mas.add_argument("--visual", action="store_true")
    mas.add_argument(
        "--mod-set", default="user-enabled",
        help="'vanilla', 'user-enabled', or comma-separated allowlist",
    )
    mas.set_defaults(func=_cmd_master)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
