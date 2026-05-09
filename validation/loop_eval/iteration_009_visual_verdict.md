# Iteration 009 -- Visual verdict

Blueprint: `library/external/factorio_school/-OsBJMo7P-2oKxsEc3oB.bp`
Label: "Tier 2 module Green Circuit. 8900/m copper wire input required. stacked belt required. Stack inserter."
Hypothetical spec: target=`electronic-circuit`, rate=40/s, mod_set=user-enabled, quality=normal.

## Verdict
status: WARN

## Spec match
- target: electronic-circuit (PASS) -- both EM-plants set to recipe `electronic-circuit` per `tools/blueprint_codec.py decode`.
- rate: requested 40/s, actual 41.48/s (PASS) -- per `rate_cli compute --recipe electronic-circuit --machine electromagnetic-plant --count 2 --modules productivity-module-2*5 --beacons "beacon*7:speed-module-2,speed-module-2"`. Tolerance margin ~+3.7%.
- machine: requested foundry as dominant, found foundry x 3 (1 molten-iron, 2 casting-iron) + electromagnetic-plant x 2 (PASS for foundry-dominant block; the actual circuit assembly is performed by EM-plants, foundries handle the iron casting feeder).
- belt tier: requested (none specified), found turbo-transport-belt x 19 + turbo-underground-belt x 4 (PASS, consistent tier).
- inserter tier: requested (none specified), found bulk-inserter x 10 + stack-inserter x 6 (WARN, mixed tiers; description says "Stack inserter" but bulk-inserters are present too).

## Structural
- bbox: 17 x 25 tiles (x_min=-128 y_min=80 x_max=-112 y_max=104) per renderer summary.
- entity counts (renderer): beacon=15, bulk-inserter=10, constant-combinator=7, electromagnetic-plant=2, foundry=3, pipe=8, pipe-to-ground=1, stack-inserter=6, turbo-transport-belt=19, turbo-underground-belt=4.
- belt continuity: not auto-validated; visual ASCII grid shows two output lanes flowing south at columns 9 and 12 (tile x=-120 and x=-117). No obvious gaps in inspected window.
- inserter reach: not auto-validated.
- power coverage: N/A -- entity_counts contains zero electric poles, zero substations. Layout is a tileable cell expecting external power; a paste-and-play user must supply substation coverage.
- fluid systems: 1 (9 pipes, 0 tanks, 0 pumps) -- carries molten-iron from the molten-iron foundry to the two casting foundries.
- circuit networks: 1 reported but `wired_entities=0`; the 7 constant-combinators carry filter signals (electronic-circuit, calcite, iron-ore, etc.) but are not wired to anything in this block (likely intended as labels/icons for the underlying belts).

## Per-stage rate calculator results
- Foundry (molten-iron, x1, 4 speed-module-2 + 2 in-range beacons -> speed x3.473): 325.6 molten-iron/s. Inputs 21.7 iron-ore/s, 0.43 calcite/s.
- Foundry (casting-iron, x2, 4 speed-module-2 each + 5 in-range beacons -> speed x4.212): 31.59 iron-plate/s. Consumes 210.6 molten-iron/s (well under 325.6/s supply).
- EM-plant (electronic-circuit, x2, 5 productivity-module-2 each + 7 in-range beacons -> speed x2.881, prod +0.80): 41.48 electronic-circuit/s. Consumes 23.05 iron-plate/s (under 31.59/s supply) and 69.14 copper-cable/s (external feed).

Per-machine beacon counts derived from beacon supply_area_distance=3 (9x9 effective box) cross-referenced with each machine's 4x4 footprint -- 15 total beacons but only 7 reach each EM-plant, 5 reach each casting foundry, 2 reach the molten-iron foundry.

## Defects (priority order)
1. Mixed inserter tiers: blueprint description claims "Stack inserter" yet `entity_counts` reports `bulk-inserter=10` alongside `stack-inserter=6`. The bulk-inserters likely serve the foundries and the stack-inserters the EM-plants; if the spec required uniform stack inserters this is a spec mismatch.
2. Constant-combinators (7) are unwired (`wired_entities=0` in circuit_networks summary); they appear to be belt labels/icons only. Not a throughput defect, but the renderer surfaces 8 warnings about unknown footprint/symbol for `constant-combinator` -- treat as informational.
3. Copper-cable input rate is 69.14/s, exceeding a single-lane turbo-transport-belt capacity of 60/s/lane (`specs/data-raw-dump.json` -> turbo-transport-belt speed=0.125). The blueprint description acknowledges this with "stacked belt required" -- so this is a documented external requirement, not an internal defect, but the user MUST feed copper-cable on a stacked belt or a 2-lane belt for the block to hit 40/s.
4. No power infrastructure: entity_counts shows 0 electric-pole/substation. Each foundry draws ~25.9 MW and each EM-plant ~21.9 MW (rate calc output) -- the user must paste this block inside an existing substation grid.
5. Renderer warnings: 4x `footprint unknown for 'turbo-underground-belt'` and 8x `unknown entity 'constant-combinator'` -- catalog gap in `tools/render_blueprint.py`/`harness/catalog.py` rather than a blueprint defect.

## Suggested fixes for generator
- If the spec demands stack-inserters everywhere, replace the 10 `bulk-inserter` entries with `stack-inserter` and re-balance throughput (stack inserters move more per swing but cost more energy/quality modules).
- For paste-and-play robustness, place at least one `substation` so all 3 foundries and 2 EM-plants are within the 18x18 supply square; current block relies on external power.
- If a self-contained block is desired, include the copper-cable feed (e.g. a copper-plate foundry stage + EM-plant for cable) so the 69.14/s demand is satisfied internally rather than via "stacked belt" external feed.
- Catalog gap (tooling, not blueprint): add `constant-combinator` (1x1) and `turbo-underground-belt` (1x1) footprints to `harness/catalog.py` so the renderer stops emitting warnings for these vanilla/Space-Age entities.
