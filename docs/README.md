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
| `scrapers.md`                | Agent F | Per-site notes on the polite scrapers under `tools/scrapers/`: discovered API endpoints, HTML parsing strategy, anti-bot observations, data hygiene caveats. | active — covers `factorio_school`, `factorioprints`, `factoriobin` |
| `rate_calculator.md`         | Agent G | Formulas, worked examples, and parity notes for `tools/rate_calculator.py` (engine behind `tools/rate_cli.py` and `harness/rates.py`). | populated; mirrors RateCalculator mod 3.3.8 with documented extensions for quality cascade and recipe-prod research |
| `visual_validator.md`        | Agent H | ASCII renderer (`tools/render_blueprint.py`) and the `blueprint-visual-validator` sub-agent that consumes it; produces structured PASS/FAIL/WARN verdicts with coordinates. | active |
| `master_orchestrator.md`     | Agent I | High-level driver (`harness/master_orchestrator.py`) that wraps `synthesize` in a generator->validator loop, plus mod-aware compatibility checks (`harness/mod_compat.py`) and a CLI for inspecting third-party blueprints. | active |
| `legacy_entity_renames.md`   | Agent J | 1.x -> 2.0 entity rename table consumed by `tools/inventory_user_blueprints.py` to remap pre-2.0 entity names (logistic chests, stack/filter inserters) when classifying user blueprints. | active |

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
for runnable builds:

- `stone_smelter_array` — 12 stone-furnaces, ore + plate belts.
- `steel_smelter_array` — 24 steel-furnaces with shared-belt coal feed.
- `electric_smelter_array` — 24 electric-furnaces with substation power.
- `solar_field` — 24 solar panels + 20 accumulators with pole coverage.
- `green_circuit_block` — 4 copper-cable + 6 electronic-circuit
  assemblers with shared cable belt.

Each docs file above is the long-form reference behind one of the
harness stages.
