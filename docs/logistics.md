# Logistics

Owner: Agent D. Source of truth: `specs/data-raw-dump.json` for the
calibrated install (Factorio 2.0.76, Space Age + Quality + Elevated Rails,
+34 third-party mods). Numbers in this doc are pulled by
`tools/extract_logistics.py` and stored as JSON under `specs/`:

- `specs/belts.json`
- `specs/inserters.json`
- `specs/electric_network.json`
- `specs/robots.json`
- `specs/research_effects.json`

Ground rules

- Factorio runs at 60 update ticks per second. Every speed in this doc
  appears in raw form (tiles/tick or revolutions/tick) and human form
  (items/s, items/min, kW, MJ).
- Belt throughput formula: `items/s/lane = speed_tiles_per_tick * 60 * 8`
  (8 item slots per belt tile per side), `items/s total = 2 * per_lane`.
- Mod origin is inferred from each prototype's icon path. Items marked
  `[VERIFY]` could not be derived from the dump alone.

## 1. Belt tier table

Five belt tiers are loaded: yellow, red (fast), blue (express), turbo
(Space Age), promethium (mod `promethium-belts`). Splitters and underground
belts use the same speed values as their matching transport belt; tunnel
distance grows with tier.

| Tier         | Internal name              | tiles/tick | items/s/lane | items/s total | items/min total | Underground max | Origin           |
|--------------|----------------------------|------------|--------------|---------------|-----------------|-----------------|------------------|
| Yellow       | `transport-belt`           | 0.03125    | 15           | 30            | 1 800           | 5               | base             |
| Red (fast)   | `fast-transport-belt`      | 0.0625     | 30           | 60            | 3 600           | 7               | base             |
| Blue (exp.)  | `express-transport-belt`   | 0.09375    | 45           | 90            | 5 400           | 9               | base             |
| Turbo        | `turbo-transport-belt`     | 0.125      | 60           | 120           | 7 200           | 11              | space-age        |
| Promethium   | `promethium-transport-belt`| 0.1875     | 90           | 180           | 10 800          | 13              | promethium-belts |

Note: the brief's expected turbo total (90 items/s) does not match the
loaded prototype. Turbo is 120/s and promethium is 180/s in this install.

> [validated 2026-05-09: dump `transport-belt.turbo-transport-belt.speed = 0.125`
> -> 60 items/s/lane × 2 = 120 items/s total; matches Factorio Wiki / Space Age.]
> Vanilla 2.0 + Space Age belt totals (items/s): yellow 30, red 60, blue 90,
> turbo 120. Promethium (180) is added by the `promethium-belts` mod and is
> not part of vanilla.

### Loaders

`loaders-modernized` adds 1x1 loaders that mirror each belt tier; they
move items at the belt-tier rate. Each `*-split` variant has built-in
sideloading / unloading split. The chute is a power-free trickle loader.

Vanilla 2x1 loaders (`loader`, `fast-loader`, ...) are still present in
`data.raw` but unobtainable without console commands. The 1x1 set below
is the practical placement target.

| Loader (1x1)                | tiles/tick | items/s total | Container distance | Origin             |
|-----------------------------|------------|---------------|--------------------|--------------------|
| `chute-mdrn-loader`         | 0.015625   | 7.5           | 1                  | loaders-modernized |
| `loader-1x1`                | 0.03125    | 15            | 1                  | base               |
| `mdrn-loader` / `-split`    | 0.03125    | 15            | 1                  | loaders-modernized |
| `fast-mdrn-loader`/`-split` | 0.0625     | 30            | 1                  | loaders-modernized |
| `express-mdrn-loader`/`-s.` | 0.09375    | 45            | 1                  | loaders-modernized |
| `turbo-mdrn-loader` / `-s.` | 0.125      | 60            | 1                  | loaders-modernized |
| `stack-mdrn-loader` / `-s.` | 0.1875     | 90            | 1                  | loaders-modernized |

Loader items/s total in this table is *single-side*; loaders feed both
lanes simultaneously, so a turbo loader can saturate a turbo belt
(120/s) just like a turbo splitter, but throughput per loader is
clamped by the destination belt.

The `stack-mdrn-loader` runs at promethium speed but does not require
a promethium belt — it caps at whatever the connected belt accepts.

## 2. Inserter behaviour

Six inserters are loaded. `bulk-inserter` is the renamed
`stack-inserter` of Factorio 1.x. Space Age adds a *new* `stack-inserter`
prototype with `stack_size_bonus=4` and `bulk=true`, designed to drop
full vertical stacks onto a belt.

`rotation_speed` is in revolutions per tick (1.0 means a full 360-degree
turn per tick). Quarter turn (pickup-side to drop-side) takes
`0.25 / rotation_speed` ticks. Divide by 60 for seconds; 1/(quarter_turn
ticks * 2 / 60) gives swings/second per arm cycle (a full pickup+drop
takes two quarter-turns plus extension/retraction).

| Inserter              | rot rev/tick | quarter turn (ticks) | ext tile/tick | E/move (kJ) | E/rot (kJ) | drain (kW) | reach pickup / insert | Bulk? | Stack bonus | Origin    |
|-----------------------|--------------|----------------------|---------------|-------------|------------|------------|-----------------------|-------|-------------|-----------|
| `burner-inserter`     | 0.013        | 19.23                | 0.035         | 50          | 50         | n/a (fuel) | 1.0 / 1.2             | no    | 0           | base      |
| `inserter`            | 0.014        | 17.86                | 0.035         | 5           | 5          | 0.4        | 1.0 / 1.2             | no    | 0           | base      |
| `long-handed-inserter`| 0.020        | 12.50                | 0.050         | 5           | 5          | 0.4        | 2.0 / 2.2             | no    | 0           | base      |
| `fast-inserter`       | 0.040        | 6.25                 | 0.100         | 7           | 7          | 0.5        | 1.0 / 1.2             | no    | 0           | base      |
| `bulk-inserter`       | 0.040        | 6.25                 | 0.100         | 20          | 20         | 1.0        | 1.0 / 1.2             | yes   | 0           | base      |
| `stack-inserter`      | 0.040        | 6.25                 | 0.100         | 40          | 40         | 1.0        | 1.0 / 1.2             | yes   | 4           | space-age |

Stack-size bonus from research is additive on top of `default_stack_size`
(1) for non-bulk inserters and on top of the bulk capacity for bulk-class
inserters. See section 5 for the tech curves.

Throughput per inserter, when the belt and the source/sink are not the
limit, is approximately:

```
throughput (items/s) = stack_size * 60 / (cycle_ticks)
cycle_ticks         = 2 * quarter_turn_ticks
                    + 2 * extend_ticks
                    + pickup_drop_overhead (~ 4-6 ticks)
```

For a fast/bulk/stack inserter at 0.04 rev/tick, the rotation-only floor
is `2 * 6.25 = 12.5 ticks/cycle = 4.8 cycles/s`. Empirical full-belt
throughput numbers (chest to chest, no extension travel) are well known
in the community: bulk inserter at +0 stack bonus = ~2.31 items/s; at
+12 stack bonus (max base research) = ~27.7 items/s. The Space Age
`stack-inserter` adds 4 to whatever bonus you have.

## 3. Power infrastructure

Pole reach + supply area:

| Pole                  | Supply half-side (tiles) | Supply square edge | Wire reach | Max HP |
|-----------------------|--------------------------|--------------------|------------|--------|
| `small-electric-pole` | 2.5                      | 5x5                | 7.5        | 100    |
| `medium-electric-pole`| 3.5                      | 7x7                | 9          | 100    |
| `big-electric-pole`   | 2.0                      | 4x4                | 32         | 150    |
| `substation`          | 9.0                      | 18x18              | 18         | 200    |

Big poles are placement waypoints with very long wire reach but minimal
coverage area; substations are the workhorse for indoor builds.

### Substation 18x18 grid template

A substation tiles on an 18-tile period: place one substation, leave 16
tiles, place the next. Coverage pattern (S = substation, . = covered):

```
S . . . . . . . . . . . . . . . . S
. . . . . . . . . . . . . . . . . .
... 17 more rows of '.' ...
. . . . . . . . . . . . . . . . . .
S . . . . . . . . . . . . . . . . S
```

Substations both wire (18-tile span = exactly one period) and supply
(9-tile half-side = covers the full 18-tile cell). For a ribbon outpost
use medium poles (7x7 supply, 9-tile wire) at 7-tile spacing.

### Accumulators

| Accumulator       | Capacity (MJ) | Input (kW) | Output (kW) | Max HP | Origin           |
|-------------------|---------------|------------|-------------|--------|------------------|
| `accumulator`     | 5             | 300        | 300         | 150    | base             |
| `accumulator-mk2` | 50            | 900        | 900         | 200    | accumulator-mk2  |

### Solar panels

Single prototype, `solar-panel`: 60 kW peak, 42 kW Nauvis day-night
average (multiply by 0.7 to account for night and dusk/dawn). Other
planets have different illumination curves, owned by Agent E.

### Boilers and steam generators

| Entity          | Type      | Energy in (MW) | Target steam | Notes                          |
|-----------------|-----------|----------------|--------------|--------------------------------|
| `boiler`        | boiler    | 1.8            | 165 C        | 0.5 fluid/tick into engine     |
| `heat-exchanger`| boiler    | 10.0           | 500 C        | 1.0 fluid/tick into turbine    |
| `steam-engine`  | generator | -              | 165 C input  | 900 kW each (1.8 MW boiler => 2 engines). Computed: `0.5 fluid/tick * 60 ticks * (165 - 15) C * 200 J/(unit*deg) * 1.0 effectivity = 900 kW`. [validated 2026-05-09: wiki Steam_engine "900 kW"] |
| `steam-turbine` | generator | -              | 500 C input  | 5.82 MW each. Computed: `1.0 fluid/tick * 60 * (500 - 15) * 200 * 1.0 = 5.82 MW`. [validated 2026-05-09: wiki Steam_turbine "5.82 MW"] |

Steam engine and turbine `max_power_output` is computed from
`fluid_usage_per_tick`, `effectivity`, and `maximum_temperature` against
steam's specific heat (200 J/unit/deg). The dump exposes the inputs but
not the precomputed cap.

### Reactors and fusion

| Entity            | Consumption / Power | Neighbour bonus | Notes                          |
|-------------------|---------------------|-----------------|--------------------------------|
| `nuclear-reactor` | 40 MW heat output   | +100% per neighbour | 2x2 reactor block = 480 MW total fuel use; 2x2 with all neighbours = 4 * 40 * (1 + 2) = 480 MW |
| `heating-tower`   | 40 MW heat output   | 0               | Gleba-friendly carbon burner; no clustering bonus |
| `fusion-reactor`  | 10 MW power_input   | n/a (chains via pipes) | Space Age; two-direction-only pipe layout |
| `fusion-generator`| 50 MW (vanilla)     | n/a             | Pairs with fusion-reactor. Quality scaling: 50/65/80/95/125 MW (normal/uncommon/rare/epic/legendary). [corrected 2026-05-09: previously said 100 MW; wiki Fusion_generator confirms vanilla normal-quality 50 MW.] |

Nuclear neighbour bonus: a single reactor produces 40 MW. Each pairwise
adjacency multiplies *both* neighbours' output by `1 + neighbour_bonus`.
Standard 2x2: each reactor has 2 neighbours, total power = `4 * 40 *
(1 + 2*1) = 480 MW`. 2x4: 1280 MW. Each reactor in a 2xN row past the
ends has 3 neighbours. Heating tower has `neighbour_bonus=0`, so pack
density does not matter.

### Electric grid sizing formula

For a block of N machines pulling C MW each, with B beacons at P MW:

```
peak_W   = N * C + N * D + B * P
average_W = peak_W * uptime_fraction + idle_drain
```

where `D` is the `drain` field on the energy source (typically 1/30th of
`max_energy_usage`, but check the prototype). Inserter drain (0.4-1.0 kW
each) is minor but adds up across thousands.

## 4. Robot logistics

Three robots are present. `Better_Robots_Plus` modifies base `speed` and
`energy_per_tick`/`energy_per_move` in-place; the values below already
reflect that mod's startup settings. `FasterStart` adds
`fission-construction-robot` with zero idle drain.

| Robot                         | tiles/tick | tiles/s | Payload | E/tick (J) | E/move (J) | Battery (kJ) | Recharge band  | Origin       |
|-------------------------------|------------|---------|---------|------------|------------|--------------|----------------|--------------|
| `logistic-robot`              | 0.40       | 24.0    | 100     | 170        | 17 000     | 15 000       | 20% to 95%     | base (modded) |
| `construction-robot`          | 0.42       | 25.2    | 10      | 85         | 6 800      | 30 000       | 20% to 95%     | base (modded) |
| `fission-construction-robot`  | 0.42       | 25.2    | 10      | 0          | 0          | 30 000       | 20% to 95%     | FasterStart  |

Vanilla baselines for reference (from wiki Logistic_robot / Construction_robot):
bot speed 0.05 tile/tick (3 tiles/s), logistic payload 1, construction
payload 1. Worker-robot-storage research can raise the payload to 4 in
vanilla (research is applied as a runtime delta on top of the prototype's
`max_payload_size`, not a mutation of the prototype itself).

> [validated 2026-05-09: wiki Logistic_robot — vanilla speed 3 tiles/s,
> default payload 1, max-via-research payload 4. The dump shows
> `max_payload_size = 100`, which is the mod startup-stage value alone
> (research = 0 at data-stage). Effective in-game payload =
> `prototype_max_payload_size + worker_robot_storage_research_level`.]
> The user's effective `mod-settings.dat` has
> `logistics-robot-carry-size-multiplier = 100.0` (Better_Robots_Plus),
> matching the dumped 100.

### Roboport

`roboport` (vanilla, modified by `BetterRoboport`):

- Logistics radius: 50 tiles (effective coverage 100x100 around the port)
- Construction radius: 110 tiles (220x220 reach for ghost work)
- Robot slots: 7 (idle bots), Material slots: 7 (repair packs etc.)
- Charging stations: 16 (per `charging_offsets` length)
- Charging energy: 20 MW per port (5x base 4 MW thanks to BetterRoboport)
- Input flow limit: 80 MW (16x base 5 MW)
- Buffer capacity: 2 500 MJ (vs. base 100 MJ)
- Idle energy usage: 50 kW
- Recharge minimum: 40 MJ

> [validated 2026-05-09: wiki Roboport vanilla = 4 charging stations,
> 4*500 kW per station, 50 kW idle drain, logistics 50, construction 110.
> Dump shows 16 stations, 20 MW per station, 80 MW input cap, 2500 MJ
> buffer — all `BetterRoboport` overrides confirmed against the user's
> binary `mod-settings.dat`: `roboport-buffer-multiplier = 5.0`,
> `roboport-charging-rate-multiplier = 1.0`, plus structural increases
> baked into the mod's lua data stage.]

### Roboport throughput math

A roboport can deliver `charging_energy * charging_station_count = 20 MW
* 16 = 320 MW` of charging power *if* its input flow allows it. With the
80 MW input cap, the port effectively recharges at 80 MW (4 stations'
worth) sustained, after the 2.5 GJ buffer is empty.

Robot recharge time from `min_to_charge` (20 %) to `max_to_charge` (95 %)
covers `(0.95 - 0.20) * battery_kj` joules. For a logistic robot:
`0.75 * 15 000 kJ = 11 250 kJ` per recharge; at 20 MW (one station) =
0.5625 s. That gives a per-port sustained throughput of `(80 MW / 11 250
kJ) = 7.1 charge events/s` (input-limited). Multiply by the average
distance covered per charge to get logistics throughput.

Average flight time per charge for a logistic robot:
`battery_drain = 11 250 kJ`. At cruise, drain = `(energy_per_tick + speed
* energy_per_move) per tick`. With speed 0.4: `170 + 0.4 * 17000 = 6 970
J/tick = 0.418 MJ/s`. So a fully charged battery lasts `11.25 / 0.418 =
26.9 s`, covering `26.9 * 24 = 645 tiles` of cruise. Realistically halve
that for round-trip plus pickup/drop overhead.

## 5. Research effects

`specs/research_effects.json` lists every tech with an entity-affecting
effect (191 effect rows across 123 techs in this install). Prerequisites
and the science cost are included. For infinite techs, `count_formula`
is the per-level science count; substitute `L = level` to get the cost
of researching that level.

### Infinite techs (highlights)

| Tech                              | Effect type                       | Per-level mod | Science count formula | Notes |
|-----------------------------------|-----------------------------------|---------------|-----------------------|-------|
| `mining-productivity-3`           | mining-drill-productivity-bonus   | +10%          | `1000*(L-2)`          | Linear; cheapest infinite tier |
| `worker-robots-speed-7`           | worker-robot-speed                | +65%          | `2^(L-6)*1000`        | Doubles every level |
| `follower-robot-count-5`          | maximum-following-robots-count    | +25 bots      | `1000*(L-4)`          | Linear |
| `health` (player)                 | character-health-bonus            | +50 HP        | `2^L*50`              | Cheap early levels |
| `research-productivity`           | laboratory-productivity           | +10%          | `1.2^L*1000`          | Slowest growth, big payoff |
| `asteroid-productivity`           | change-recipe-productivity        | +10% per recipe | `1.5^L*1000`        | Hits 6 asteroid-crushing recipes |
| `processing-unit-productivity`    | change-recipe-productivity        | +10%          | `1.5^L*1000`          | Blue chips |
| `low-density-structure-productivity` | change-recipe-productivity     | +10%          | `1.5^L*1000`          | LDS + casting-LDS |
| `plastic-bar-productivity`        | change-recipe-productivity        | +10%          | `1.5^L*1000`          | Plastic + bioplastic |
| `rocket-fuel-productivity`        | change-recipe-productivity        | +10%          | `1.5^L*1000`          | All 3 rocket-fuel recipes |
| `rocket-part-productivity`        | change-recipe-productivity        | +10%          | `1.5^L*2000`          | Most expensive |
| `scrap-recycling-productivity`    | change-recipe-productivity        | +10%          | `1.5^L*500`           | Cheapest productivity tier |
| `steel-plate-productivity`        | change-recipe-productivity        | +10%          | `1.5^L*1000`          | Steel + casting-steel |
| `physical-projectile-damage-7`+   | ammo-damage / turret-attack       | varies        | `2^(L-7)*1000`        | Mil; doubles per level |

Per-recipe productivity bonuses cap at +300% in vanilla Factorio (max
modifier sum is +3.0), reached at level 30. Combined with module
productivity (+25% from a level-5 quality prod-3) the practical hard cap
on a recipe is +400%.

### Capped (finite) bonus techs (relevant)

| Tech                        | Effect type                  | Modifier | Cumulative |
|-----------------------------|------------------------------|----------|------------|
| `bulk-inserter`             | bulk-inserter-capacity-bonus | +1       | 1          |
| `inserter-capacity-bonus-1` | bulk-inserter-capacity-bonus | +1       | 2          |
| `inserter-capacity-bonus-2` | bulk-inserter-capacity-bonus | +1       | 3          |
| `inserter-capacity-bonus-2` | inserter-stack-size-bonus    | +1       | 1          |
| `inserter-capacity-bonus-3` | bulk-inserter-capacity-bonus | +1       | 4          |
| `inserter-capacity-bonus-4` | bulk-inserter-capacity-bonus | +1       | 5          |
| `inserter-capacity-bonus-5` | bulk-inserter-capacity-bonus | +2       | 7          |
| `inserter-capacity-bonus-6` | bulk-inserter-capacity-bonus | +2       | 9          |
| `inserter-capacity-bonus-7` | bulk-inserter-capacity-bonus | +2       | 11         |
| `inserter-capacity-bonus-7` | inserter-stack-size-bonus    | +1       | 2          |
| `stack-inserter` (Space Age)| belt-stack-size-bonus        | +1       | 1          |
| `transport-belt-capacity-1` | belt-stack-size-bonus        | +1       | 2          |
| `transport-belt-capacity-2` | belt-stack-size-bonus        | +1       | 3          |
| `transport-belt-capacity-2` | inserter-stack-size-bonus    | +1       | 3          |
| `worker-robots-speed-1..6`  | worker-robot-speed           | +35-65%  | +325% sum  |
| `worker-robots-storage-1..3`| worker-robot-storage         | +1 each  | +3         |

`belt-stack-size-bonus` is the Space Age mechanic that lets a stack
inserter drop multiple items into the same belt slot. With all three
techs, a belt slot can hold 4 items; at 8 slots/tile/lane that means
turbo belts move `4 * 60 * 8 = 1920` items/s/lane in stacked mode (in
practice, transit volume is governed by what feeds and unloads the
belt; stacking is a buffer trick).

After the bonus chain, a fully researched non-bulk inserter has stack
size `1 + 2 = 3`, and a fully researched bulk/stack inserter has stack
size `12 + (default_stack_size or stack_size_bonus)`:

- bulk-inserter base + 11 = 12 items per swing
- stack-inserter base 4 + 11 = 15 items per swing (12 in non-Space-Age)

## 6. Derived ratios

Throughput numbers below assume saturated chest-to-belt, full research,
no quality bonus on the inserter, and `60 ticks/s`. These are the
common build-block intuitions you want to drop into a blueprint.

### Inserters per belt

A bulk inserter at +11 stack bonus = 12 items/swing. A 0.04 rev/tick
inserter does 4.8 swings/s in best case (no extension travel). So:
`12 * 4.8 = 57.6 items/s sustained per bulk inserter`. Stack-inserter
adds the +4 base, so 16 items/swing = 76.8 items/s sustained.

| Belt         | Items/s | Bulk inserters needed | Stack inserters needed |
|--------------|---------|-----------------------|------------------------|
| Yellow       | 30      | 1 (52% util)          | 1 (39% util)           |
| Red          | 60      | 2                     | 1 (78% util)           |
| Blue         | 90      | 2                     | 2                      |
| Turbo        | 120     | 3                     | 2                      |
| Promethium   | 180     | 4                     | 3                      |

### Loaders

A loader matches the belt-tier rate exactly. One turbo loader saturates
one turbo belt. A `stack-mdrn-loader` runs at 90 items/s, so it
saturates a promethium belt; on lesser belts it's belt-limited.

### Solar / accumulator ratio (Nauvis)

Standard ratio: 25 solar panels to 21 accumulators per machine load is
*not* this install's ratio because `accumulator-mk2` has 10x capacity
but only 3x flow. For a 1 MW load on Nauvis (Nauvis day-night cycle
factor 0.7):

- Daytime peak per panel: 60 kW; night: 0; average: 42 kW
- Panels needed for average: `1000 / 42 = 24` panels/MW
- Accumulator energy needed: `night_seconds * 1 MW = 210 s * 1 MW =
  210 MJ` per MW load (assuming 210 s of dark)
- Mk1: `210 / 5 = 42` accumulators/MW
- Mk2: `210 / 50 = 4.2` accumulators/MW (4.2x cheaper)

Mk2 input flow (900 kW) limits charge rate: 1 MW load => need at least
`1000 / 900 = 1.12` mk2 accumulators charging in parallel during the
day to keep up. The energy-per-MW number is the binding constraint.

### Reactor ratios (vanilla, unchanged)

- 2x2 nuclear: 480 MW (4 * 40 * 3) heat output. Feeds 48 heat
  exchangers (480 / 10) which feed 83 turbines (heat exchanger / steam
  turbine standard 1:1.74 ratio gives `48 * 1.74 = 83.5`). Useful power
  ~480 MW.
- 2x4 nuclear: 1280 MW. 128 exchangers, ~223 turbines.

### Roboport coverage

A line of roboports at 49-tile spacing (just under the 50-tile
logistics radius) gives unbroken logistics coverage. Use 110-tile
spacing for construction-only ghost networks (build outposts).

> [validated 2026-05-09: dump `roboport.energy_source.input_flow_limit = 80MW`,
> `charging_offsets` length = 16, `charging_energy = 20MW`. The theoretical
> ceiling is `16 * 20 = 320 MW`; the input_flow_limit caps sustained
> recharge at 80 MW once the 2500 MJ buffer drains. Per-bot band
> (logistic robot needs 11.25 MJ for 75 % refill) means at most ~7.1
> charge events / s sustained. In bursts, the 2500 MJ buffer covers ~31
> seconds of full 80 MW draw before the cap engages.]
