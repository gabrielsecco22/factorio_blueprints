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
