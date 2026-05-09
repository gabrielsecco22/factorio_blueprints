#!/usr/bin/env python3
"""Run one /loop iteration: creator -> calculator -> visual reviewer.

Reads state.json for the iteration counter, picks the next test case from
TEST_CASES, runs it through the toolchain, writes a per-iteration report,
and bumps state.json.

Run from repo root:
    python3 validation/loop_eval/run_iteration.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
STATE = REPO / "validation/loop_eval/state.json"
LOGDIR = REPO / "validation/loop_eval"

# Each case: human label + a callable that returns the concrete commands
# (label, [commands]) where each command is (description, argv-or-shell).
# Cases rotate so each loop firing exercises a different facet.
TEST_CASES = [
    ("green_circuit_block_5ps_vanilla", [
        ("creator: master_synthesize (--kind required for non-smelter cases)",
         ["python3", "-m", "harness.master_orchestrator", "master",
          "--target", "electronic-circuit", "--rate", "5",
          "--mod-set", "vanilla", "--kind", "green_circuit_block"]),
        ("calculator: belt-saturate",
         ["python3", "tools/rate_cli.py", "belt-saturate",
          "--recipe", "electronic-circuit",
          "--machine", "assembling-machine-2",
          "--belt-tier", "transport-belt"]),
    ]),
    ("intentionally_impossible_spec", [
        ("creator: master_synthesize (should fail or warn)",
         ["python3", "-m", "harness.master_orchestrator", "master",
          "--target", "processing-unit", "--rate", "1000",
          "--machine", "assembling-machine-1", "--mod-set", "vanilla",
          "--kind", "green_circuit_block",  # closest planner; will likely fail
          "--max-iter", "2"]),
    ]),
    ("steel_smelter_array_run_only", [
        ("creator: example",
         ["python3", "-m", "harness.examples.steel_smelter_array"]),
    ]),
    ("solar_field_run_only", [
        ("creator: example",
         ["python3", "-m", "harness.examples.solar_field"]),
    ]),
    ("inspect_real_user_blueprint_factorio_school", [
        ("inspect", "python3 -m harness.master_orchestrator inspect "
                    "$(ls library/external/factorio_school/*.bp 2>/dev/null | head -1)"),
    ]),
    ("inspect_real_user_blueprint_factoriobin", [
        ("inspect", "python3 -m harness.master_orchestrator inspect "
                    "$(ls library/external/factoriobin/*.bp 2>/dev/null | head -1)"),
    ]),
]


def _run(cmd) -> tuple[int, str]:
    """Run a command (list or shell-string), capture combined output, truncate."""
    try:
        if isinstance(cmd, list):
            r = subprocess.run(cmd, cwd=REPO, capture_output=True,
                               text=True, timeout=120)
        else:
            r = subprocess.run(cmd, cwd=REPO, shell=True, capture_output=True,
                               text=True, timeout=120)
        out = (r.stdout or "") + ("\n[stderr]\n" + r.stderr if r.stderr else "")
        if len(out) > 4000:
            out = out[:4000] + "\n[... truncated ...]"
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 124, "[timeout after 120s]"
    except FileNotFoundError as e:
        return 127, f"[command not found: {e}]"


def _render_first_blueprint(text: str) -> tuple[int, str]:
    """Find a blueprint string in the text and render it."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("0e") and len(line) > 100:
            return _run(["python3", "tools/render_blueprint.py", "--json", line])
    return 0, "[no blueprint string found in output to render]"


def main() -> int:
    state = json.loads(STATE.read_text()) if STATE.exists() else {
        "iteration": 0, "cases_done": []
    }
    n = state["iteration"] + 1
    case_idx = (n - 1) % len(TEST_CASES)
    label, commands = TEST_CASES[case_idx]
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = [
        f"# Loop iteration {n:03d}",
        "",
        f"- **timestamp**: {started}",
        f"- **case**: `{label}` (index {case_idx + 1}/{len(TEST_CASES)})",
        "",
    ]

    captured_outputs = []
    for desc, cmd in commands:
        rc, out = _run(cmd)
        captured_outputs.append(out)
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        report += [
            f"## {desc} (exit {rc})",
            "",
            "```",
            cmd_str,
            "```",
            "",
            "```",
            out,
            "```",
            "",
        ]

    # Visual reviewer step: render any blueprint we produced
    combined = "\n".join(captured_outputs)
    rc, render_out = _render_first_blueprint(combined)
    report += [
        f"## visual reviewer: render_blueprint --json (exit {rc})",
        "",
        "```",
        render_out,
        "```",
        "",
    ]

    # Quick verdict heuristic
    failures = [o for o in captured_outputs if "FAIL" in o or "error" in o.lower()
                or "shortfall" in o.lower()]
    verdict = "PASS"
    if failures:
        verdict = "WARN"
    if "[timeout" in combined:
        verdict = "FAIL"
    report += [
        f"## verdict: {verdict}",
        "",
    ]

    out_path = LOGDIR / f"iteration_{n:03d}.md"
    out_path.write_text("\n".join(report))

    # Append to running log
    log_path = LOGDIR / "eval_log.md"
    line = f"- iter {n:03d} ({started}) {label} -> {verdict} -> {out_path.name}\n"
    if not log_path.exists():
        log_path.write_text("# Loop eval log\n\n")
    with log_path.open("a") as f:
        f.write(line)

    state["iteration"] = n
    state["cases_done"] = state.get("cases_done", []) + [label]
    STATE.write_text(json.dumps(state, indent=2) + "\n")

    print(f"iter {n:03d} {label} -> {verdict}")
    print(f"  report: {out_path}")
    print(f"  log:    {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
