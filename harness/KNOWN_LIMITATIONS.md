# Known limitations of the harness MVP

These are the rough edges of the first synthesizable blueprint set
(`stone_smelter_array`, `solar_field`). They produce blueprints that
pass `validate.py` and the JSON Schema, but are not fully turn-key.

## Smelter array

- **No fuel feed.** The 12-furnace stone-smelter array has an ore feed
  belt and a plate output belt. Coal still has to be supplied to each
  furnace manually after pasting (or by laying a separate fuel belt
  parallel to the ore belt). A future version should:
  - Reserve a third belt lane for fuel, OR
  - Spawn one extra burner-inserter per furnace facing the ore belt
    and configure a filter for `coal`, OR
  - Switch to electric-furnace and skip fuel entirely (needs power).
- **Fixed inserter type.** Stone-smelter array uses
  `burner-inserter` so that the array is power-free; this means each
  inserter is also burner-fueled and needs fuel along with each furnace.
  The `electric_smelter_array` example (TODO) should use plain
  inserters and an electric pole network.
- **No request chests / wagons.** The array is fed exclusively by belts.

## Solar field

- **No connectivity wires emitted.** Medium-electric-poles are placed
  with adequate supply-area coverage, but the harness emits no
  `wires` array, so each pole is its own electrical network on paste.
  The game will auto-connect adjacent poles in-place once the user
  pastes the blueprint, so this works in practice (poles within
  `wire_reach_tiles` auto-connect on placement). For a power network
  that survives copy/paste between distant locations, an explicit
  `wires` entry per adjacent pole pair is needed.
- **Accumulator/panel ratio.** The default 24:20 ratio is the wiki's
  classic figure for Nauvis day/night cycles with a slight surplus.
  It is NOT recomputed from the current dump's day/night settings.

## Future builders mentioned in the prompt but not yet implemented

- `steel_smelter_array.py` — needs fuel feed wiring.
- `electric_smelter_array.py` — needs power coverage on top of layout.
- `green_circuit_block.py` — needs a two-stage planner that chains
  two production cells (copper-cable -> electronic-circuit) with a
  shared belt segment.
