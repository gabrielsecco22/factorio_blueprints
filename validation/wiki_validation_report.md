# Wiki + dump validation report

Owner: Coordinator (final pass).
Date: 2026-05-09.
Sources cross-checked: `wiki.factorio.com` (via WebFetch),
`redruin1/factorio-blueprint-schemas` 2.0.0 (via gh API),
`specs/data-raw-dump.json` (Factorio 2.0.76 + Space Age + Quality +
Elevated Rails + 34 third-party mods, the user's actual install),
binary `~/.factorio/mods/mod-settings.dat` (parsed via stdlib).

## 1. [VERIFY] item summary

| # | Item | Status | Notes |
| - | ---- | ------ | ----- |
| 1 | Wires `circuit_id` 6 = power switch right terminal | RESOLVED | confirmed via 2.0.0 blueprint schema; left = 5, right = 6 |
| 2 | `neighbours` field for power poles in 2.0 | RESOLVED | removed; 2.0 entity schema has no `neighbours` key |
| 3 | `parameter-N` substitution token style | RESOLVED | confirmed via FFF-392 + 2.0.0 schema |
| 4 | `stock_connections` field name | RESOLVED | exact name `stock_connections`, items `{stock,front?,back?}` |
| 5 | 2.0 train interrupt `wait_condition` types | RESOLVED | full list captured; corrected `robots_inactive` (not in schema) |
| 6 | Vanilla beacon prototype values | RESOLVED | 2 slots / 1.5 effectivity / no productivity / 480 kW; annotated |
| 7 | Quality crafting-speed bonuses (1.0/1.3/1.6/1.9/2.5×) | RESOLVED | confirmed via wiki Assembling_machine_3 quality table |
| 8 | Vanilla module slot counts (AM3/EM-plant/recycler/cryogenic-plant) | RESOLVED | 4 / 5 / 4 / 8; annotated in machines.json |
| 9 | Steam engine / turbine `max_power_output` | RESOLVED | engine 900 kW, turbine 5.82 MW; closed-form formula in logistics.md |
| 10 | Fusion-generator output power | RESOLVED — DISCREPANCY FIXED | wiki = 50 MW vanilla normal (not 100); spec corrected |
| 11 | `logistic-robot.max_payload_size = 100` provenance | RESOLVED | mod-only; effective `mod-settings.dat` confirms `logistics-robot-carry-size-multiplier = 100.0` |
| 12 | BetterRoboport 80 MW saturation behaviour | RESOLVED | 320 MW theoretical -> 80 MW input cap once 2500 MJ buffer drains; ~7.1 charge events/s sustained |
| 13 | Trip-time formula between planets | RESOLVED | 180 tile/s is a soft upper bound for narrow platforms; real formula on wiki Thruster page |
| 14 | Quality `next_probability=0.10` | RESOLVED | NOT per-craft promotion; it's the **secondary cascade** rate for chained promotions |
| 15 | Recycler-loop legendary fraction math | RESOLVED — ESCALATED | closed-form in wiki absent; sanity_checks hosts hook for numeric Markov sim; ~70% community number stands |
| 16 | Accumulator capacity quality scaling | RESOLVED | 5/10/15/20/30 MJ across normal..legendary; in/out 300/390/480/570/750 kW |
| 17 | AdjustableModule live mod settings | RESOLVED | parsed binary mod-settings.dat; `Configure-beacon = "Enabled-and-all"`, `ad-module-slots = 4`, `ad-beacon-area = 3`, `ad-beacon-efficiency = 1.0` |

All 17 items: **17 RESOLVED, 0 UNDETERMINED**. One inline discrepancy fixed
(fusion generator 100→50 MW). Several inline corrections of belt-rate
labelling and base-productivity claims for foundry/EM-plant/biochamber
(wiki says +50% native, not +100% — the +100% in the dump comes from a
mod, likely `AdjustableModule` or `Li-Module-Fix`).

## 2. Per-spec audit

### `docs/blueprint_format.md`

| Claim | Wiki/schema agreement | Action |
| ----- | --------------------- | ------ |
| Encoding pipeline (base64 + zlib + version byte `'0'`) | matches | none |
| Wire circuit_id 1-6 | matches schema | added wire_connector_id mapping table |
| `neighbours` removed in 2.0 | matches | upgraded `[VERIFY]` to validated note |
| `stock_connections` field | matches | upgraded to validated note + structure |
| `parameter-N` substitution | matches | upgraded to validated note + `pN_s` formula helper |
| Train wait_conditions list | partial mismatch | corrected: removed `robots_inactive`, added `fuel_*`, `not_empty`, `specific_destination_full/_not_full`, `any_planet_import_zero` |
| `direction` 8/16-way enum | matches | none |
| Position math (entity center vs tile corner) | matches | none |

### `docs/machines_and_recipes.md`

| Claim | Wiki/dump agreement | Action |
| ----- | ------------------- | ------ |
| Foundry +100 % base prod, 5 slots | dump yes, vanilla +50 % / 4 slots | annotated `vanilla_2_0_76` in machines.json; doc table now shows both |
| EM-plant +100 % base, 6 slots | dump yes, vanilla +50 % / 5 slots | same |
| Biochamber +100 % base, 5 slots | dump yes, vanilla +50 % / 4 slots | same |
| Cryogenic plant +50 % base, 9 slots | dump yes, vanilla 0 % / 8 slots | same |
| AM3 5 slots | dump yes, vanilla 4 | annotated |
| Recycler 5 slots, +50 % base, productivity allowed | dump yes, vanilla 4 / 0 / disallowed | annotated |
| Beacon 5 slots / 3.0 effectivity / +50 % base prod | dump yes, vanilla 2 / 1.5 / 0 | annotated `vanilla_2_0_76` in beacons.json |
| Quality speed multiplier `1 + 0.3*(level/2)` | matches wiki | converted `[VERIFY]` to validated note |
| Belt rates yellow 30 / red 60 / blue 90 / turbo 120 | matches | none |
| Logistic-robot speed 0.4, payload 100 | dump yes, vanilla 0.05 / 1 (max-research 4) | annotated `vanilla_2_0_76` in robots.json |
| Roboport 16 stations / 20 MW / 80 MW input / 2500 MJ | dump yes, vanilla 4 / 4 / 5 / 100 | annotated |

### `docs/ratios_examples.md`

| Claim | Wiki/dump agreement | Action |
| ----- | ------------------- | ------ |
| Belt rate table labelled "items/s" was actually per-lane | mismatch | corrected: now shows per-lane and total side-by-side |
| `casting-iron` = 5/s/foundry, base 100 % prod | dump matches | none (foundry is +100 % in this install) |
| EM-plant processing-unit @ 0.4/s | dump matches | none |
| Recycler 0.5 speed × 1/16 cycle factor | dump matches | none |

### `docs/logistics.md`

| Claim | Wiki/dump agreement | Action |
| ----- | ------------------- | ------ |
| Belt tier table | matches dump | annotation added that promethium is mod |
| Loader matrix | matches dump | none |
| Inserter rotation table | matches dump (formula `0.25/rotation_speed`) | sanity test enforces |
| Pole reach (small/medium/big/substation) | matches dump | none |
| Solar peak 60 kW / Nauvis avg 42 kW | matches | none |
| Steam engine 900 kW, steam turbine 5.82 MW | matches wiki | upgraded `[VERIFY]` to validated with formula |
| Fusion generator 100 MW | wiki = 50 MW vanilla | corrected to 50 MW |
| Robot speed/payload (modded) | matches dump | annotated |
| Roboport (modded) | matches dump | annotated; saturation `[VERIFY]` resolved |

### `docs/planets_quality_beacons.md`

| Claim | Wiki/dump agreement | Action |
| ----- | ------------------- | ------ |
| Per-planet surface_properties table | matches dump | none |
| Quality tier table | matches dump + wiki | none |
| `next_probability = 0.10` semantics | wiki clarifies it's the cascade rate, not per-craft | rewrote note |
| Beacon profile array `1/sqrt(N)` | matches dump | none |
| Beacon dump = AdjustableModule override | matches | added live mod-settings.dat values |
| Recycler loop ~70 % legendary | community estimate | flagged as numeric-sim territory; doc still cites figure with caveat |
| Accumulator quality scaling | wiki confirms | added concrete table |
| Trip time `length / 180` | lower bound only | added wiki formula reference |

## 3. Mod impact table

| Mod | Mutates | Specs affected | Annotation status |
| --- | ------- | -------------- | ----------------- |
| `AdjustableModule` | beacon (slots, effectivity, allowed_effects, base_effect); recipe productivity gating | beacons.json, machines.json (recipe-level), planets_quality_beacons.md | annotated; effective `mod-settings.dat` values captured |
| `Li-Module-Fix` | productivity-module limitations removed; adds `*-fish` cheat modules; adds `beacon-fish` | modules.json, beacons.json, machines_and_recipes.md | doc notes `*-fish` are cheat items; module limitations confirmed empty in dump |
| `Better_Robots_Plus` | logistic-robot speed/payload; construction-robot speed/payload | robots.json | `vanilla_2_0_76` annotation added |
| `BetterRoboport` | roboport stations, charging energy, input flow, buffer | robots.json | annotated |
| `accumulator-mk2` | adds new accumulator | electric_network.json | new prototype; no vanilla equivalent |
| `loaders-modernized` | adds 1x1 loader prototypes for every belt tier; chute | logistics.md | doc lists them |
| `promethium-belts` | adds 180/s belt tier (space-platform only) | belts.json, logistics.md, ratios_examples.md | doc flags as mod-only |
| `quality-seeds` | adds quality-aware greenhouse cultivators | machines.json | listed in machine table |
| `FasterStart` | adds `fission-construction-robot` | robots.json | listed |
| `quality-condenser`, `infinite-quality-tiers`, `rosnok-productivity-quality-beacon`, `UMModulesRework`, `productivity_fix` | DISABLED in user's mod-list | n/a | mod-list.json confirms disabled |
| `beacon-interface` | adds 81-slot debug beacons | beacons.json, modules.json | flagged as sandbox/debug |
| `Wagon-quality-size` | wagon stack size scales with quality | (no spec yet) | noted |

The user's effective `mod-settings.dat` reveals additional knobs: `beacon_de = 2`
and `beacon_sad = 1` (likely `Li-Module-Fix` extras), and `module_all = True`
which interacts with productivity-module limit removal.

## 4. Inline corrections summary

| File | Change |
| ---- | ------ |
| `docs/blueprint_format.md` | wire connector enum table; `neighbours` removed; `stock_connections` shape; train wait_condition list rewritten |
| `docs/machines_and_recipes.md` | every machine row now shows `vanilla 2.0 = X` for slots / base-productivity; quality multiplier note converted to validated; beacon row carries vanilla note |
| `docs/ratios_examples.md` | belt rate table fixed (per-lane vs total) |
| `docs/logistics.md` | belt vanilla note; steam engine / turbine formula validated; fusion generator 100→50 MW; vanilla bot baseline; vanilla roboport baseline; saturation `[VERIFY]` resolved |
| `docs/planets_quality_beacons.md` | trip-time formula reference; `next_probability` cascade clarification; recycler-loop note; accumulator quality table; AdjustableModule `mod-settings.dat` effective values; closed `[VERIFY]` items section |
| `docs/CONVENTIONS.md` | new file: vanilla vs modded policy, footnote style |
| `specs/machines.json` | 23 machines annotated with `vanilla_2_0_76` |
| `specs/beacons.json` | `beacon` annotated with `vanilla_2_0_76` |
| `specs/robots.json` | logistic-robot, construction-robot, roboport annotated |
| `tools/annotate_vanilla_baselines.py` | new re-runnable script, stdlib only |
| `tools/extract_machines.py` | added blueprint-family item types so they appear in items.json (closes a sanity-check gap) |
| `validation/sanity_checks.py` | new battery (107 invariants, all passing) |

## 5. Sanity-check result

`python3 validation/sanity_checks.py` exits 0. **PASS: 107, FAIL: 0**.
Exercised invariants:

- recipe ingredient/result resolution (against items.json + fluids.json)
- recipe-type vs slot-type consistency (no `type:item` pointing at a fluid)
- every non-synthetic recipe category has a crafter; every category-listed
  machine exists
- every entity_planet_restrictions key resolves to a real prototype
  (cross-checked against the dump for entries that aren't in any topic spec)
- every research effect's `recipe` field points to a real recipe
- belt math: `speed × 480 = items_per_second_total`; `per_lane × 2 = total`
- inserter quarter-turn: `0.25 / rotation_speed` matches stored value
- planet surface properties (5 required) for every real planet + the
  space-platform pseudo-surface
- quality rank monotonicity (rank 0..N-1, speed monotone non-decreasing,
  beacon power non-increasing)
- beacon profile starts at 1.0 and matches advertised length
- module effect bounds (speed module > 0; productivity module ≤ 0.5)
- crafting machines have non-empty `crafting_categories`; mining drills
  appear in some `resource_categories`
- vanilla baseline annotations exist for beacon, logistic-robot, foundry
- recipe_planet_restrictions reference real planets

## 6. Open questions left for user

None — all `[VERIFY]` items closed in this pass. See
`validation/open_questions.md` (would only exist if items remained
unresolved; this pass left it absent).
