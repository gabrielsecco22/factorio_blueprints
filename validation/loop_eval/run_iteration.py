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
    # === Matrix v2: added 2026-05-09 after rotation 1 reached steady state ===
    ("render_real_factorio_school_blueprint", [
        # The factorio.school blueprint is a single blueprint (not a book), so
        # the renderer should consume it directly rather than refusing.
        ("render: structural summary",
         "python3 tools/render_blueprint.py --json "
         "$(ls library/external/factorio_school/*.bp 2>/dev/null | head -1)"),
        ("render: ASCII grid (first 80 cols)",
         "python3 tools/render_blueprint.py --max-width 80 --grid-only "
         "$(ls library/external/factorio_school/*.bp 2>/dev/null | head -1)"),
    ]),
    ("quality_legendary_iron_plate", [
        # Exercise quality multipliers via the rate calculator. A legendary
        # stone-furnace runs at base_speed * 2.5 = 5 plates / (3.2/2.5)s.
        ("calculator: legendary stone-furnace",
         ["python3", "tools/rate_cli.py", "compute",
          "--recipe", "iron-plate",
          "--machine", "stone-furnace",
          "--machine-quality", "legendary",
          "--count", "1"]),
        ("calculator: 3-furnace compare (--machine is repeatable)",
         ["python3", "tools/rate_cli.py", "compare",
          "--recipe", "iron-plate",
          "--machine", "stone-furnace",
          "--machine", "steel-furnace",
          "--machine", "electric-furnace"]),
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


def _render_first_blueprint(text: str, command_str: str = "") -> tuple[int, str]:
    """Find a blueprint string in the text and render it.

    Order of precedence:
      1. blueprint string emitted by the previous command (`0e...` line)
      2. inspect-case fallback: re-run the same `$(...)` shell expression
         as render_blueprint's argument, so it reads the `.bp` file directly
    """
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("0e") and len(line) > 100:
            return _run(["python3", "tools/render_blueprint.py", "--json", line])

    if isinstance(command_str, str) and "$(" in command_str and ".bp" in command_str:
        # Extract the `$(...)` substring verbatim and let the shell re-expand
        # it for the renderer. Same expression -> same file.
        start = command_str.index("$(")
        depth = 0
        end = start
        for i, ch in enumerate(command_str[start:], start):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        shell_expr = command_str[start:end]
        return _run(f"python3 tools/render_blueprint.py --json {shell_expr}")
    return 0, "[no blueprint string or file path found to render]"


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

    # Visual reviewer step: render any blueprint we produced. For inspect
    # cases we pass the original shell command so the fallback can re-expand
    # the `$(ls ...)` to the actual .bp file path.
    combined = "\n".join(captured_outputs)
    last_cmd = commands[-1][1] if commands else ""
    cmd_for_render = last_cmd if isinstance(last_cmd, str) else ""
    rc, render_out = _render_first_blueprint(combined, cmd_for_render)
    report += [
        f"## visual reviewer: render_blueprint --json (exit {rc})",
        "",
        "```",
        render_out,
        "```",
        "",
    ]

    # Verdict heuristic. Include the renderer's output too -- a render error
    # used to slip past because we only inspected captured_outputs.
    all_text = combined + "\n" + render_out
    bad_signals = ("FAIL", "error", "shortfall", "Traceback", "ValueError",
                   "ModuleNotFoundError", "[stderr]")
    failed = any(sig.lower() in all_text.lower() for sig in bad_signals)
    verdict = "WARN" if failed else "PASS"
    # Render error on an inspect case where the input was a known book is
    # expected behavior, not a defect: the inventory marks books as
    # envelope-only / kind=blueprint-book and the renderer refuses them.
    if ("inspect" in label
            and "blueprint-book not supported" in render_out):
        verdict = "PASS"
    if "[timeout" in all_text:
        verdict = "FAIL"
    if rc != 0 and "blueprint-book not supported" not in render_out:
        verdict = "WARN" if verdict == "PASS" else verdict
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
