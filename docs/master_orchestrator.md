# Master orchestrator

`harness.master_orchestrator` is the high-level driver on top of the
single-shot `harness.synthesize`. Use it whenever you want a
self-correcting loop, mod-aware safety checks, or a CLI for inspecting
external blueprints.

## When to use which

| You want to...                              | Use                              |
| ------------------------------------------- | -------------------------------- |
| Build one blueprint from a known-good spec  | `harness.synthesize(BuildSpec)`  |
| Build with a target rate, retry on failure  | `master_synthesize(MasterSpec)`  |
| Reject any non-vanilla output               | `mod_set="vanilla"`              |
| Inspect a blueprint someone shared with you | `python3 -m harness.master_orchestrator inspect <bp>` |

`synthesize` is deterministic and never retries; `master_synthesize`
wraps it in a feedback loop and adds compatibility gates.

## The loop

```
   +---------+    +-----------+    +---------+
   | spec    |--->| synthesize|--->| validate|------+
   +---------+    +-----------+    +---------+      |
        ^                                           v
        |                                     +-----------+
        |                                     | rate calc |
        |                                     +-----------+
        |                                           |
        |                                           v
        |                                     +-----------+
        |                                     | mod check |
        |                                     +-----------+
        |                                           |
        |                                           v
        |  parse "Suggested fixes"            +-----------+
        +-----<-------------------------------| visual?   |
                                              +-----------+
```

Each iteration aggregates four checks into an `IterationVerdict`:

1. **Structural** -- `harness.validate.validate` (collisions, belt
   continuity, inserter reach, pole coverage, JSON Schema if installed).
2. **Rate** -- `harness.rates.rates_for_plan` is asked whether the
   produced plan meets `MasterSpec.output_rate_per_sec`.
3. **Mod** -- every entity / recipe / module in the encoded blueprint
   is attributed via `harness.mod_compat`. The verdict fails if the
   `mod_set` policy disallows any required mod.
4. **Visual** -- only runs when `enable_visual_validator=True`. The
   real validator is a Claude Code subagent (see
   `.claude/agents/blueprint-visual-validator.md`); the loop calls a
   Python fallback that shells out to `tools/render_blueprint.py` if
   present, otherwise emits a soft-pass placeholder. Treat the visual
   leg as best-effort until the renderer lands.

When a verdict fails, the loop parses the verdict's `## Suggested
fixes` section into `Constraint` objects and folds them into the next
iteration's spec. The MVP recognises three constraint kinds:

- `min_machine_count` -- "at least N furnaces / machines / assemblers"
- `require_fuel_belt` -- "needs a fuel belt", "coal feed", etc.
- `switch_belt_tier` -- "switch to <belt-name>"

Anything else is stored as a `raw` constraint so the trace shows it
verbatim, but the loop will not act on it.

The loop stops at the first `PASS`, after `max_iterations`, or when an
iteration produces no new actionable fixes (we don't loop forever on
the same suggestion).

## Mod-set semantics

`MasterSpec.mod_set` controls what counts as an "available" mod when
the post-synthesis check runs. Supported values:

- `"vanilla"` -- only `base`, `core`, and the bundled DLC mods
  (`space-age`, `quality`, `elevated-rails`) are allowed. Use this
  when you want a blueprint that any Space-Age player can paste.
- `"user-enabled"` -- everything in the user's
  `~/.factorio/mods/mod-list.json` with `enabled=true`, plus DLC.
  Use this when you're building for your own factory.
- `list[str]` -- explicit allowlist. Anything else is rejected.

The check is symmetric: required mods come from the produced
blueprint, available mods come from the policy. If they don't match,
the iteration fails with a structured `mod_compat` report.

DLC are special: `space-age`, `quality`, and `elevated-rails` ship
with the install at `<install>/data/`, NOT in the user's mods folder.
They are detected via `tools/detect_factorio.py`'s `dlc.*` flags and
treated as always-available when the user owns the DLC. They are
never substituted (you cannot replace `quality` with anything).

## CLI: inspect

```sh
python3 -m harness.master_orchestrator inspect <blueprint-string-or-path>
```

Decodes the blueprint, walks every entity/recipe/module reference,
and reports the source mod for each plus its current state in the
user's install. Output looks like:

```
Blueprint requires:
  base                       (enabled in user install)
  space-age                  (enabled in user install)
  promethium-belts           (INSTALLED but DISABLED -- enable to use this blueprint)
  Bottleneck                 (INSTALLED but DISABLED)
  SuperWidgetMod             (NOT INSTALLED -- blueprint will fail to import without this)

Suggested vanilla equivalents available for: promethium-transport-belt -> turbo-transport-belt

User install: /home/<you>/.factorio/mods
  enabled=38 disabled=19 zip-only=0 dlc=['elevated-rails', 'quality', 'space-age']
```

The four states a mod can be in:

| State     | Meaning |
| --------- | ------- |
| enabled   | mod-list.json has `enabled=true`, OR mod is bundled DLC |
| disabled  | mod-list.json has `enabled=false`; the .zip is on disk |
| zip-only  | .zip in mods/ but not yet listed in mod-list.json (game adds on next launch) |
| missing   | referenced in the blueprint but not installed at all -- the paste will fail |

Use `inspect` before importing any blueprint from the wild.

## CLI: master

```sh
python3 -m harness.master_orchestrator master \
    --target iron-plate --rate 30 \
    --mod-set vanilla \
    --machine stone-furnace
```

Runs the loop and prints the iteration trace plus the resulting
blueprint string. Exit code 0 on `PASS` or `WARN`, 1 on `FAIL`.

Useful flags:

- `--max-iter N` (default 3) -- max iterations.
- `--visual` -- enable the visual-validator leg (currently a soft pass
  until the renderer ships).
- `--mod-set vanilla|user-enabled|<comma list>`.

## Python API

```python
from harness.master_orchestrator import master_synthesize, MasterSpec

result = master_synthesize(MasterSpec(
    target="iron-plate",
    output_rate_per_sec=30,
    machine_choice="stone-furnace",
    fuel="coal",
    max_iterations=3,
    mod_set="vanilla",
))

result.final_status        # "PASS" | "FAIL" | "WARN"
result.blueprint_string    # paste-ready (or None on FAIL with no candidate)
result.iterations          # list[IterationRecord]; each has .verdict, .spec
result.report              # markdown trace
result.mod_compat          # {required, available, missing, disabled, zip_only}
```

## Known gaps

- The visual-validator subagent cannot be called from Python at all.
  The loop's `_fallback_visual` returns a soft pass when the renderer
  isn't installed; once `tools/render_blueprint.py` lands, wire it up
  there. The fallback's "Suggested fixes" parser is intentionally
  trivial -- the real fixes will come from the agent.
- `Constraint.apply_to` only knows three nudges. Add more kinds as
  the validator's vocabulary grows.
- Mod attribution falls back to `base` when a prototype is in the
  dump but lacks a `from_mod` tag. If your dump has many such cases
  (some mods don't tag prototypes correctly), expect `base` to be
  over-counted in the inspect output.
