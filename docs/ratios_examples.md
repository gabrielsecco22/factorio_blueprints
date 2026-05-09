# Ratio Examples

Belt-saturation and quality-cascade tables computed from
`specs/recipes.json` and `specs/machines.json` for this user's mod set.

All "machines per belt" values are rounded to two decimals; in practice
build the ceiling and let the belt back-pressure regulate. **Each table
already includes the machine's `effect_receiver.base_effect.productivity`
(50% for most, 100% for foundry / EM-plant / biochamber).** Module bonuses
are listed separately per row.

## Belt rates (full belt, both lanes)

| Belt tier | items/s/lane | items/s total |
| --- | ---: | ---: |
| yellow (transport-belt) | 15 | 30 |
| red (fast-transport-belt) | 30 | 60 |
| blue (express-transport-belt) | 45 | 90 |
| turbo (turbo-transport-belt) | 60 | 120 |
| promethium (promethium-transport-belt) | 90 | 180 |

> [corrected 2026-05-09: previous table showed only per-lane numbers
> but labelled them "items/s" and conflated with totals. Per the dump
> `transport-belt.<tier>.speed` × 480 = items/s total. Wiki numbers
> match.]

## 1. Smelting / metallurgy

### iron-plate (smelting category)

| Machine | Modules | items/s/machine | yellow | red | blue | turbo |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| stone-furnace | none | 0.469 | 32.00 | 64.00 | 96.00 | 128.00 |
| steel-furnace | none | 0.938 | 16.00 | 32.00 | 48.00 | 64.00 |
| electric-furnace | none | 0.938 | 16.00 | 32.00 | 48.00 | 64.00 |
| electric-furnace | 3x speed-3 | 2.344 | 6.40 | 12.80 | 19.20 | 25.60 |

### casting via foundry (metallurgy)

Foundry has +100% base productivity. `casting-iron`/`casting-copper` produce
2 plates per 20 molten metal in 3.2 s; `molten-iron` from a foundry
yields 500 molten-iron per 32 s (with +100% base = 1000).

| Recipe | Machine | Modules | items/s | yellow | red | blue | turbo |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| casting-iron | foundry | none | 5.00 | 3.00 | 6.00 | 9.00 | 12.00 |
| casting-iron | foundry | 4x prod-3 | 2.40 | 6.25 | 12.50 | 18.75 | 25.00 |
| casting-copper | foundry | none | 5.00 | 3.00 | 6.00 | 9.00 | 12.00 |
| casting-steel | foundry | none | 2.50 | 6.00 | 12.00 | 18.00 | 24.00 |
| molten-iron | foundry | none | 125.0 fluid/s | n/a | n/a | n/a | n/a |

> A pair of foundries on `casting-iron` saturate one yellow belt of iron
> plates from a single ore stream, while a half-dozen feed a turbo belt.

## 2. Circuits

| Recipe | Machine | Modules | items/s | yellow | red | blue | turbo |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| copper-cable | assembling-machine-3 | none | 7.50 | 2.00 | 4.00 | 6.00 | 8.00 |
| copper-cable | electromagnetic-plant | none | 16.00 | 0.94 | 1.88 | 2.81 | 3.75 |
| electronic-circuit | assembling-machine-3 | none | 3.75 | 4.00 | 8.00 | 12.00 | 16.00 |
| electronic-circuit | electromagnetic-plant | none | 8.00 | 1.88 | 3.75 | 5.62 | 7.50 |
| advanced-circuit | assembling-machine-3 | none | 0.312 | 48.00 | 96.00 | 144.00 | 192.00 |
| advanced-circuit | assembling-machine-3 | 5x prod-3 | 0.156 | 96.00 | 192.00 | 288.00 | 384.00 |
| advanced-circuit | electromagnetic-plant | none | 0.667 | 22.50 | 45.00 | 67.50 | 90.00 |
| advanced-circuit | electromagnetic-plant | 4x prod-3 | 0.400 | 37.50 | 75.00 | 112.50 | 150.00 |
| processing-unit | assembling-machine-3 | none | 0.188 | 80.00 | 160.00 | 240.00 | 320.00 |
| processing-unit | electromagnetic-plant | none | 0.400 | 37.50 | 75.00 | 112.50 | 150.00 |
| processing-unit | electromagnetic-plant | 4x prod-3 | 0.192 | 78.13 | 156.25 | 234.38 | 312.50 |

> **Module-slot trap.** Stuffing more than four prod-3s into the
> electromagnetic plant *reduces* output: each prod-3 is `-15% speed`, and
> the engine clamps machine speed at 20% of base. With 6x prod-3 the speed
> floor kicks in (`max(0.2, 1 + 6 * -0.15) = 0.2`), so `2.0 * 0.2 = 0.4` is
> the speed; productivity adds linearly but cannot recover the lost
> throughput. Beacons or speed modules in the remaining slots are needed to
> unlock the extra prod slots.

## 3. Late-game intermediates

### low-density-structure

| Machine | Modules | items/s | yellow | red | blue | turbo |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| assembling-machine-3 | none | 0.125 | 120.00 | 240.00 | 360.00 | 480.00 |
| foundry (`casting-low-density-structure`) | none | 0.533 | 28.13 | 56.25 | 84.38 | 112.50 |

### rocket-fuel

| Machine | Modules | items/s | yellow | red | blue | turbo |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| assembling-machine-3 | none | 0.125 | 120.00 | 240.00 | 360.00 | 480.00 |
| biochamber (with bioflux) | none | 0.267 | 56.25 | 112.50 | 168.75 | 225.00 |

## 4. Science packs (assembling-machine-3, no modules)

| Pack | items/s | yellow | red | blue | turbo |
| --- | --- | ---: | ---: | ---: | ---: |
| automation-science-pack | 0.375 | 40.00 | 80.00 | 120.00 | 160.00 |
| logistic-science-pack | 0.312 | 48.00 | 96.00 | 144.00 | 192.00 |
| chemical-science-pack | 0.156 | 96.00 | 192.00 | 288.00 | 384.00 |
| production-science-pack | 0.268 | 56.00 | 112.00 | 168.00 | 224.00 |
| utility-science-pack | 0.268 | 56.00 | 112.00 | 168.00 | 224.00 |

## 5. Biochamber recipes

| Recipe | items/s | yellow | red | blue | turbo |
| --- | --- | ---: | ---: | ---: | ---: |
| bioflux | 2.667 | 5.62 | 11.25 | 16.88 | 22.50 |
| nutrients-from-bioflux | 80.00 | 0.19 | 0.38 | 0.56 | 1.12 |

> One biochamber on `nutrients-from-bioflux` produces enough nutrients to
> keep ~120 other biochambers fueled. Plan a single small loop near the
> bioflux source; do not pipe nutrients across long belts (5 minute spoil
> timer).

## 6. Recycler quality cascades

The recycler runs a paired `<item>-recycling` recipe that returns 25% of
each ingredient (`probability: 0.25`). Modules apply normally. Quality
modules give the returned items a chance to upgrade quality.

### Effective recycler throughput (raw items consumed/s, base 50% prod)

| Source recipe time (s) | Recycling time (s) at recycler speed 0.5 | items consumed/s |
| --- | --- | --- |
| 0.5 | 0.0625 | 16.0 |
| 1.0 | 0.125 | 8.0 |
| 3.2 (smelting) | 0.4 | 2.5 |
| 6.0 (advanced-circuit) | 0.75 | 1.33 |
| 10.0 (processing-unit) | 1.25 | 0.80 |
| 15.0 (LDS, rocket-fuel) | 1.875 | 0.53 |

### Recycler-loop sizing (legendary cascade with 4x quality-3)

A single quality-3 module is `+0.25` quality, displayed as `+2.5%` per
slot. Four slots = 10% chance per craft to upgrade by one tier. The fifth
slot can hold productivity-3 (+10% productivity) for free returns or another
quality-3.

For a `processing-unit -> processing-unit-recycling` legendary loop, you
need to feed each recycler the equivalent of one EM-plant of normal
processing units. Throughput per machine when both are running 4x quality-3:

| Stage | Machine | items/s | Notes |
| --- | --- | ---: | --- |
| craft (normal) | electromagnetic-plant | 0.32 | base 100% prod, 4x quality-3 (-20% speed) |
| recycle (normal) | recycler | 4.80 | of the input throughput; returns 25% per cycle |

Steady-state ratio for a balanced cascade where every "non-promoted" output
is recycled back into ingredients:

```
N_recyclers / N_em-plants = (em-plant processing-unit/s) / (recycler input/s)
                          = 0.32 / 4.80
                          ~= 1 recycler per 15 EM-plants
```

If the loop targets only the *finished* item upgrades (not ingredient
upgrades), and one EM-plant outputs `q` legendary processing units per
craft, the total cascade size is approximately:

```
runs_to_legendary = 4 (uncommon -> rare -> epic -> legendary)
upgrade_chance = 0.025 * num_quality_modules per stage
expected_machines = 1 / (upgrade_chance ** runs_to_legendary)
```

For 4x quality-3 modules at every stage (`upgrade_chance = 0.10`), the
expected machine count to produce a single legendary item per craft is
`1 / 0.10^4 = 10000` cycles input. In practice the recycler loop replays
inputs many times, so the effective input multiplier is closer to
`1 / (1 - return_fraction_per_cycle)`. For processing-unit-recycling with
4x quality-3 + base 50% prod, return fraction is `0.25 * 1.5 = 0.375`, so
the input multiplier is `1 / (1 - 0.375) = 1.6` - a quality cascade
consumes roughly 60% extra raw inputs over a single pass.

> **[VERIFY]** The closed-form quality cascade math above approximates the
> Markov chain over quality tiers. The toolkit should host a
> `quality_loop_simulator()` that runs the chain numerically; pencil-and-
> paper estimates suffice for blueprint sizing.

## 7. Recipes worth memorising

| Recipe | Default machine | items/s/machine | One full belt needs |
| --- | --- | ---: | --- |
| copper-cable | EM-plant | 16.0 | 1 EM-plant per yellow |
| electronic-circuit | EM-plant | 8.0 | 2 EM-plants per yellow |
| advanced-circuit | EM-plant | 0.667 | 23 EM-plants per yellow |
| processing-unit | EM-plant | 0.4 | 38 EM-plants per yellow |
| iron-plate (casting) | foundry | 5.0 | 3 foundries per yellow |
| copper-plate (casting) | foundry | 5.0 | 3 foundries per yellow |
| steel-plate (casting) | foundry | 2.5 | 6 foundries per yellow |
| LDS (casting) | foundry | 0.533 | 29 foundries per yellow |

These numbers assume bare machines with the in-built base productivity from
this dump. With four prod-3 modules each, divide the "per belt" count by
roughly `(1.4) / (1 + speed_penalty)` for foundry/biochamber and
`(1.6) / (1 - 0.6)` clamp for EM-plant cases - or just regenerate the table
from the catalog.
