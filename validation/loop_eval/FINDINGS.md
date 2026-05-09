# Loop eval findings

Running tally of issues surfaced by the /loop eval driver, plus what was
done about each. Updated by the loop-running agent each pass.

## Fixed

- **iter 001** — `tools/rate_cli.py` raised `ModuleNotFoundError: No module named 'tools'`
  when run directly. Same import-path bug as `validation/test_rate_calculator.py`
  had earlier. Fixed by inserting `sys.path.insert(0, repo_root)` at the top of
  `rate_cli.py`. (Symptom found by the calculator step; same bug class as a
  previous fix — should add a project-wide convention.)

- **iter 001** — `validation/loop_eval/run_iteration.py` belt-saturate command
  was missing the required `--machine` argument. Fixed in the eval driver.

- **iter 002** — `validation/loop_eval/run_iteration.py` master command was
  passing `--max-iterations` but the actual flag is `--max-iter`. Fixed in the
  eval driver.

## Validated by later iterations

- **iter 003** (`steel_smelter_array_run_only`) passed cleanly — first PASS
  in the loop. Confirms the deterministic creator + renderer + rate-calc
  chain works end-to-end on a known-good example. The visual-reviewer step
  produced a sensible structural JSON (bbox, entity_counts).
- **iter 004** (`solar_field_run_only`) PASS, mods_referenced=base only.
- **iter 005** (`inspect_real_user_blueprint_factorio_school`) PASS;
  exposed an eval-driver gap: inspect commands don't emit a blueprint
  string, so the renderer was never called. Fixed by adding a
  shell-expression fallback that re-expands `$(ls ...)` for the renderer.
- **iter 006** (`inspect_real_user_blueprint_factoriobin`) exposed two
  more issues:
  - Render fallback fix worked end-to-end; renderer correctly errored
    `blueprint-book not supported` since the factoriobin demo IS a book.
    This is expected behavior, not a defect.
  - Verdict heuristic only inspected captured_outputs, ignoring the
    renderer's stderr — false PASS. Fixed: include render output in the
    bad-signal scan, plus a special case for the expected book-not-
    supported error so it doesn't trigger WARN.

## Loop reached steady state

- **iter 007** (`green_circuit_block_5ps_vanilla`, second go) PASS.
  Re-test of the iter-1 case after fixes: `--kind green_circuit_block`
  in the eval driver, sys.path setup in rate_cli.py, and tightened
  verdict heuristic. Every step exits 0; iteration trace reports
  `attempt 1: status=PASS, struct=True, rate=True, mod=True, visual=True`.
  All 3 bugs from rotation 1 are validated as fixed.

After 7 iterations the loop is producing repeat PASSes on the existing
test matrix. To keep extracting value, the next thing to do is broaden
the matrix. Suggested additions:

- A quality-aware case (legendary stone-furnace / uncommon assembling-machine)
- A beacon-heavy case to exercise the Space Age single-machine
  transmission profile
- A user-modded case using `--mod-set user-enabled` and a planner that
  can take advantage of `accumulator-mk2` or `promethium-belts`
- Decode + render an actual factorio.school blueprint (not just inspect)
  to push the renderer's coverage of larger / more diverse entity sets
- Replace the deterministic visual-reviewer step with a real call into
  the `.claude/agents/blueprint-visual-validator.md` sub-agent so we
  get the structured Markdown verdict the agent produces

## Matrix v2 (added iter 8)

Two new cases added after the loop reached steady state:

- **iter 008** (`quality_legendary_iron_plate`) WARN. Real findings:
  - **Quality math validates end-to-end**: legendary stone-furnace
    runs at 0.7812 plates/s vs normal 0.3125 = exactly 2.5x, matching
    `specs/quality.json::legendary.machine_speed_multiplier=2.5`.
  - Test-case bug: my driver passed `--machines a,b,c` (plural,
    comma-separated) but `rate_cli.py compare` uses `--machine`
    (singular, repeatable via `action="append"`). Fixed in driver.
    The CLI is correct; the test was wrong.
  - Note from compare output: stone-furnace shows 90 kW power, same
    as steel-furnace, even though both are burner machines and don't
    consume electricity. This is the documented rate-calc TODO: it
    reports electric-equivalent power for burner machines instead of
    fuel/s. See `docs/rate_calculator.md` "Diverges" section.

- **`render_real_factorio_school_blueprint`** (out-of-rotation verification):
  the renderer handles the full 2.0/Space Age entity set cleanly on the
  real Green Circuit 2400/m blueprint. Reports 15 beacons + 3 foundries
  + 2 EM-plants + 6 stack-inserters + 4 turbo-undergrounds + 19 turbo-belts
  + 1 pipe-to-ground + 7 constant combinators + 8 pipes + 10 bulk-inserters,
  bbox 17x25 (negative coordinates: x=-128..-112). No unknowns, no warnings.

## Iter 9 — first real visual-validator agent run

The deterministic step PASSed (green_circuit_block rotation 2). In
parallel the real visual-validator agent ran on the actual factorio.school
Vulcanus blueprint against a hypothetical 40/s spec. Verdict at
`iteration_009_visual_verdict.md`.

Status: **WARN**. Real findings:

- Plausibility validated end-to-end. Per-machine beacon coverage
  computed from `supply_area_distance=3` + the dumped beacon positions:
  7 beacons reach each EM-plant, 5 each casting foundry, 2 the molten-
  iron foundry. With prod-2 loadout, the 2 EM-plants produce **41.48
  electronic-circuit/s** -- 3.7% headroom over the 40/s label.
- Mixed inserter tiers: 10 bulk-inserter + 6 stack-inserter despite the
  description claiming "stack inserter only".
- Copper-cable demand 69.14/s exceeds a single turbo-belt lane (60/s);
  description acknowledges this as an external-feed requirement.
- Zero electric poles in the blueprint -- ~110 MW load assumes
  existing grid at the paste site.

**New tool bug surfaced**: `master_orchestrator inspect --json` errors
out -- the `--json` flag is unsupported. The agent fell back to plain
`inspect` and continued. Worth adding `--json` to the inspect CLI for
machine-readable consumption in future loops.

**Workflow finding (project-scoped agents don't auto-load mid-session)**:
Tried `subagent_type=blueprint-visual-validator` via the Agent tool;
it errored "Agent type not found". Project-scoped agents in
`.claude/agents/` only register at session start. Worked around by
launching a `general-purpose` agent with the agent's prompt content
inlined. For future sessions, restarting Claude Code picks up the
project agent automatically.

## Iter 10 — fixed iter-9's tool bug

The visual-validator agent flagged that `master_orchestrator inspect
--json` was unsupported. Acted on it before iter 11:

- **Fixed**: `harness/master_orchestrator.py::_cmd_inspect` now accepts
  `--json` and emits the `InspectionReport` as a structured JSON tree
  via `dataclasses.asdict` with a `_json_safe` default for `set` and
  nested dataclasses. Verified end-to-end on the factorio.school
  blueprint -- output starts with `attribution.by_mod.space-age:
  [turbo-transport-belt, turbo-underground-belt, foundry, ...]` (i.e.
  the real data, not a stringified repr).
- Regression tests: `test_master_orchestrator` 6/6, `test_inventory`
  passes, `test_render` 13/13. No regressions.

Iter 10 itself ran `intentionally_impossible_spec` (rotation 2) -> WARN
as designed; it's an intentional negative case.

## Architectural follow-ups discovered

- `master_orchestrator inspect` calls "Unknown entities" but does NOT
  apply the 1.x->2.0 rename table that `tools/inventory_user_blueprints`
  + `docs/legacy_entity_renames.md` already maintain. Sharing the table
  via `harness/mod_compat.py` would let inspect surface the modern names
  inline (e.g. `logistic-chest-passive-provider` -> `passive-provider-chest`).

## Open issues to track

- **Master orchestrator planner-dispatch is target-agnostic.** When a user
  passes `--target electronic-circuit` without `--kind green_circuit_block`,
  the orchestrator silently defaults to `--kind smelter_array`, which then
  fails downstream because the smelter planner places electric inserters
  without poles. There should be a target-to-kind inference table (or a
  registry that planner authors register their target items into) so the
  CLI can pick the right planner automatically.

- **Repeating import-path pattern.** Both `tools/rate_cli.py` and
  `validation/test_rate_calculator.py` shipped without sys.path setup,
  even though sibling files in `validation/` had it. Worth either:
  (a) a project convention documented in `CLAUDE.md` ("every entrypoint
  script must inject sys.path"), or (b) a `conftest.py` / `_pathfix.py` shim
  that all entrypoints can `import` once.

## Cases queued (rotation, 6 total)

1. green_circuit_block_5ps_vanilla
2. intentionally_impossible_spec
3. steel_smelter_array_run_only
4. solar_field_run_only
5. inspect_real_user_blueprint_factorio_school
6. inspect_real_user_blueprint_factoriobin

After case 6, the rotation wraps and case 1 should now succeed (the kind
flag was added). One full rotation = 6 iterations.
