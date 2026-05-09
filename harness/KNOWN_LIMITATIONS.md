# Known limitations of the harness MVP

These are the rough edges of the synthesizable blueprint set
(`stone_smelter_array`, `steel_smelter_array`, `electric_smelter_array`,
`solar_field`, `green_circuit_block`). All five produce blueprints that
pass `validate.py` and the JSON Schema.

## Smelter arrays

- **Stone smelter has no fuel feed.** The 12-furnace stone-smelter array
  has an ore feed belt and a plate output belt, but no coal delivery.
  The user must supply coal manually after pasting (or upgrade to the
  steel-smelter variant which does run a fuel-feed inserter).
- **Steel smelter uses shared-belt fuel feed only.** The fuel inserter
  is filtered for `coal` and pulls from the same belt as the iron-ore.
  Players need to run two lanes on the input belt: ore on one side,
  coal on the other. A `"separate"` `fuel_feed` mode also exists in the
  planner but is not exercised by an example yet.
- **Electric smelter uses no modules.** Each electric furnace has 2
  module slots; the MVP leaves them empty. A follow-up should fill
  module slots with productivity / speed modules and add beacons.
- **No request chests / wagons.** Arrays are fed exclusively by belts.

## Solar field

- **No connectivity wires emitted.** Medium-electric-poles are placed
  with adequate supply-area coverage, but the harness emits no `wires`
  array, so each pole is its own electrical network on paste. The game
  auto-connects adjacent poles in-place once the user pastes the
  blueprint, so this works in practice (poles within `wire_reach_tiles`
  auto-connect on placement). For a power network that survives
  copy/paste between distant locations, an explicit `wires` entry per
  adjacent pole pair is needed.
- **Accumulator/panel ratio.** The default 24:20 ratio is the wiki's
  classic figure for Nauvis day/night cycles with a slight surplus.
  It is NOT recomputed from the current dump's day/night settings.

## Green circuit block

- **Cable-starved by design.** The 4 cable + 6 circuit assembler ratio
  matches the prompt but produces only 16 cable/s vs. 18 cable/s
  demand; the plan emits a warning. An assembling-machine-2 variant
  would balance the ratio (or use 5 cable + 6 circuit at tier 1).
- **Fixed assembler tier.** Hard-coded to assembling-machine-1; the
  spec accepts `machine_choice` overrides but only 3x3 footprints work
  with the current layout.
- **No connectivity wires.** Substations placed at the four corners of
  the bounding box auto-connect when pasted but are otherwise
  unconnected in the blueprint string.

## Validate.py reach assumptions

- `check_inserter_reach` now uses the inserter's per-prototype
  `pickup_distance_tiles` / `insert_distance_tiles` (rounded to integer
  tiles). Long-handed inserters validate correctly.
