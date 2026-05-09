# Spec conventions

How to read the JSON files in `specs/` and the markdown in `docs/`.

## Modded vs vanilla baseline

Numeric values in `specs/*.json` and `docs/*.md` come from the user's
**actual** prototype dump (`specs/data-raw-dump.json`), which reflects
Factorio 2.0.76 + Space Age + Quality + Elevated Rails + ~34 third-party
mods enabled at dump time. Several of those mods mutate base prototypes:

| Mod                 | What it changes                                                                  |
| ------------------- | -------------------------------------------------------------------------------- |
| `AdjustableModule`  | Beacon: 5 slots, 3.0 effectivity, allows productivity + quality, +50% base prod  |
| `Li-Module-Fix`     | Removes module limitations; adds `*-fish` cheat modules; adds `beacon-fish`      |
| `Better_Robots_Plus`| Logistic robot speed 0.4, payload 100; construction robot speed 0.42, payload 10 |
| `BetterRoboport`    | Roboport 16 stations, 20 MW each, 80 MW input, 2500 MJ buffer                    |
| `accumulator-mk2`   | Adds 50 MJ accumulator                                                           |
| `loaders-modernized`| Adds 1x1 loaders for every belt tier                                             |
| `promethium-belts`  | Adds 180/s belt tier (space-platform only)                                       |
| `quality-seeds`     | Greenhouse cultivators with quality propagation                                  |
| `FasterStart`       | `fission-construction-robot` with zero idle drain                                |

Wherever a modded value diverges from vanilla, the spec records the
**modded value as the primary field** and the vanilla baseline as a
sibling `vanilla_2_0_76` object. The annotator
(`tools/annotate_vanilla_baselines.py`) is re-runnable.

Example (`specs/beacons.json`):

```json
{
  "name": "beacon",
  "module_slots": 5,
  "distribution_effectivity": 3,
  "vanilla_2_0_76": {
    "module_slots": 2,
    "distribution_effectivity": 1.5,
    "allowed_effects": ["consumption", "speed", "pollution"],
    "note": "vanilla 2.0 beacon: 2 slots..."
  }
}
```

Blueprint-synthesis tooling should pick the variant that matches its
target install:

- **Portable blueprints** (intended to paste on any Space Age save):
  use `vanilla_2_0_76`.
- **This-user blueprints** (will only ever paste on this exact mod set):
  use the top-level fields.

If `vanilla_2_0_76` is absent, the top-level value matches vanilla.

## Markdown footnote markers

- `> [validated YYYY-MM-DD: source]` — value was checked against the
  cited source on that date.
- `> [corrected YYYY-MM-DD: previously said X, now Y]` — value was
  changed in this validation pass; old value retained for traceability.
- `[VERIFY]` (legacy marker) — should be empty after the latest
  validation pass; if you see one, treat it as a TODO.

## Other conventions

- Python: stdlib only, target 3.10+. See `CLAUDE.md`.
- Bash: `set -euo pipefail`.
- No emojis in committed files.
- Prototype names are case-sensitive and use the dump's keys verbatim.
- Belt math: `items/s_total = speed_tiles_per_tick * 480`.
- Inserter math: `quarter_turn_ticks = 0.25 / rotation_speed`.
- Quality multipliers: `1 + 0.3 * (level / 2)` for crafting speed,
  module effects, and beacon strength bonus.
