# docs/

Curated, human-readable specs for the Factorio blueprint toolkit. Each
file targets one game system and is calibrated against the live prototype
dump at `../specs/data-raw-dump.json` (Factorio 2.0.76, Space Age +
Quality + Elevated Rails, 34 third-party mods).

## Index

| File | Owner | Purpose | Status |
| ---- | ----- | ------- | ------ |
| `blueprint_format.md`        | Agent B | Wire format for blueprint strings: base64 + zlib + JSON envelope, entity layout, signal IDs, train schedules, upgrade/deconstruction planners. | in progress — populated by agent B |
| `machines_and_recipes.md`    | Agent C | Crafting machines, recipes, energy and pollution, module slots, belt throughput, balanced production-line ratios. | in progress — populated by agent C |
| `logistics.md`               | Agent D | Belts, inserters, pipes, logistic bots, train signals, circuit network signals and combinator semantics. | in progress — populated by agent D |
| `planets_quality_beacons.md` | Agent E | Per-planet rules (Nauvis, Vulcanus, Fulgora, Gleba, Aquilo), quality tiers and stat multipliers, beacon stacking and transmission ranges. | populated by agent E; derived JSON in `specs/planets.json`, `specs/quality.json`, `specs/beacons.json`, `specs/recipe_planet_restrictions.json`, `specs/entity_planet_restrictions.json` (regenerate via `tools/extract_planets.py`) |

Add new specs here with a one-line description in the table above. Keep
each spec scoped to a single system; cross-link rather than duplicate.

## Source of truth

Numbers in these docs must trace back to `../specs/data-raw-dump.json`
(or `../specs/mod-settings-dump.json` for tunables). When in doubt, prefer
the dump over the wiki.

## Synthesis harness

The `harness/` directory at the repo root consumes these specs to
synthesize valid blueprint strings from a `BuildSpec`. See
`../harness/README.md` for the architecture and `../harness/examples/`
for runnable builds (smelter array, solar field). Each docs file
above is the long-form reference behind one of the harness stages.
