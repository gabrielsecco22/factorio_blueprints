# Rate calculator

Reference for `tools/rate_calculator.py`. The engine computes inputs,
outputs, power, pollution, and quality cascade for any single-recipe
production cell. It backs the `tools/rate_cli.py` CLI and the
`harness.rates` wrapper that the orchestrator embeds in synthesis
reports.

## Engine constants

| Constant            | Value | Source                                 |
|---------------------|-------|----------------------------------------|
| `SPEED_FLOOR`       | 0.2   | Engine; matches in-game module GUI.    |
| `QUALITY_CAP`       | 0.248 | Engine cap on per-craft cascade chance.|
| `PROD_CAP_DEFAULT`  | 3.0   | Default `recipe.maximum_productivity` in 2.0+ (engine constant); some recipes set their own (e.g., `gmo-*` recipes set 0). |

All three are configurable on `RateInput` for mods that change them.

## Symbolic formulas

Notation: `M` = machine prototype, `R` = recipe, `Q` = machine quality
tier, `mods` = list of `(module, quality)`, `bcns` = list of
`Beacon(name, quality, count, modules)`.

### 1. Effect aggregation

For one module `m` at quality `q`:

    eff_m,q,k = base_effect(m).k * quality(q).module_effect_multiplier
    for each effect k in {speed, productivity, consumption, pollution, quality}

For one beacon group `(name, q, N, beacon_mods)`:

    profile_idx     = clamp(N - 1, 0, len(profile) - 1)
    eff_beacon      = (distribution_effectivity
                       + n_quality_levels * distribution_effectivity_bonus_per_quality_level)
    per_module_share = eff_beacon * profile[profile_idx]
    beacon_strength_q = quality(q).beacon_strength_multiplier
    contribution.k  = sum_modules eff_m,q,k * per_module_share * N * beacon_strength_q
                       (one term per module in the beacon, NOT per machine)

Plus the beacon's own `effect_receiver.base_effect` (e.g., the modded
`AdjustableModule` beacon adds `productivity 0.5`):

    base_contribution.k = beacon_base.k * per_module_share * N * beacon_strength_q

The Space Age beacon profile is `1/sqrt(N)` for `N >= 1`:

    profile = [1.0, 0.7071, 0.5773, 0.5, 0.4472, 0.4082, 0.3779, 0.3535,
               0.3333, ..., 0.1]   (length 100)

### 2. Caps and floors

Sum module + beacon + machine `base_effect` + per-recipe research
productivity into raw bonuses. Then:

    speed_mult     = max(SPEED_FLOOR, 1 + raw_speed_bonus)
    prod           = min(raw_prod_bonus, recipe.maximum_productivity or PROD_CAP_DEFAULT)
                     # then clipped to [0, cap]
    cons_mult      = max(0.2, 1 + raw_cons_bonus)
    pollution_mult = max(0, 1 + raw_pollution_bonus)
    quality_chance = clip(raw_quality_bonus, 0, QUALITY_CAP)

### 3. Throughput

    machine_speed = M.crafting_speed * quality(Q).machine_speed_multiplier
    crafts_per_sec = (machine_speed * speed_mult) / R.energy_required
    crafts_per_sec_total = crafts_per_sec * machine_count

### 4. Inputs and outputs

Productivity does **not** affect ingredient consumption (matches
RateCalculator and the engine):

    inputs[item]_per_sec  = sum_ing crafts_per_sec * ing.amount * machine_count

Outputs apply productivity only to the part beyond
`product.ignored_by_productivity`:

    expected         = product.probability * 0.5 * (amount_max + amount_min)
                       + product.extra_count_fraction
    prod_complement  = min(expected, ignored_by_productivity)
    prod_base        = expected - prod_complement
    amount_per_craft = prod_complement + prod_base * (1 + prod)
    outputs[item]_per_sec = crafts_per_sec * amount_per_craft * machine_count

### 5. Quality cascade

For item-typed outputs only, with chance `c`:

    P(stay)        = 1 - c
    P(up 1 tier)   = c * (1 - 0.1)
    P(up 2 tiers)  = c * 0.1 * (1 - 0.1)
    P(up 3 tiers)  = c * 0.1 * 0.1 * (1 - 0.1)
    P(up 4 tiers)  = c * 0.1 * 0.1 * 0.1     (terminal)

We model up to four cascades (covers normal -> legendary) and clamp at
the highest available tier.

### 6. Power and pollution

    per_machine_power = M.energy_usage_kw * cons_mult + M.drain_kw
    beacon_power      = sum_b N * beacon.energy_usage_kw * quality(b.q).beacon_power_usage_multiplier
    total_power       = per_machine_power * machine_count + beacon_power
    pollution_per_min_per_machine = M.pollution * pollution_mult * speed_mult * cons_mult

## Worked examples

### Yellow assembler making copper-cable

    machine_speed = 0.5 * 1.0 = 0.5
    crafts_per_sec = 0.5 / 0.5 = 1.0
    outputs.copper-cable = 1.0 * 2 = 2.0/s
    inputs.copper-plate  = 1.0 * 1 = 1.0/s

### Foundry on molten-iron-from-lava (vanilla 2.0)

    base prod = 0.5 (vanilla overlay)
    machine_speed = 4.0
    crafts_per_sec = 4 / 16 = 0.25
    outputs.molten-iron = 0.25 * 250 * (1 + 0.5) = 93.75/s
    outputs.stone       = 0.25 * 10  * (1 + 0.5) = 3.75/s
    inputs.lava         = 0.25 * 500             = 125/s

### EM plant + 5 prod-3 + 12 vanilla beacons (2 speed-3 each)

    raw_speed_bonus  = 5 * (-0.15) + 12 * (1.5 * 0.2886) * (2 * 0.5) = 4.4448
    speed_mult       = 5.4448
    raw_prod_bonus   = 0.5 (base) + 5 * 0.1 = 1.0   (under cap, kept)
    machine_speed    = 2 * 1.0 = 2
    crafts_per_sec   = 2 * 5.4448 / 0.5 = 21.7792
    outputs.electronic-circuit = 21.7792 * 1 * (1 + 1.0) = 43.5584/s

## Belt-saturation tables

Belt prototypes available in this install (per `specs/belts.json`):

| Belt                       | items/s/lane | items/s total |
|----------------------------|--------------|----------------|
| transport-belt (yellow)    | 15           | 30             |
| fast-transport-belt (red)  | 30           | 60             |
| express-transport-belt (blue) | 45        | 90             |
| turbo-transport-belt       | 60           | 120            |
| promethium-transport-belt  | 90           | 180            |

To get a belt-saturation report for any recipe / machine combination:

    python3 tools/rate_cli.py belt-saturate \
        --recipe iron-plate --machine steel-furnace --count 24 \
        --belt-tier express-transport-belt

The CLI prints one row per output item with the belts-needed and
lanes-needed.

## Parity with the RateCalculator mod

The reference implementation is the in-game RateCalculator mod by
raiguard, version 3.3.8 (the user's installed copy). The relevant Lua is
`scripts/calc-util.lua`'s `process_crafter`. Salient lines:

    local recipe_duration = recipe.energy / entity.crafting_speed
    local productivity = 1 + math.min(
        entity.productivity_bonus + recipe.productivity_bonus,
        recipe.prototype.maximum_productivity
    )
    local extra_count_fraction_contribution = product.extra_count_fraction or 0
    local max_amount = product.amount_max or product.amount
    local min_amount = product.amount_min or product.amount
    local expected_amount = (product.probability or 1) * 0.5 * (max_amount + min_amount)
                            + extra_count_fraction_contribution
    local productivity_base_complement = math.min(expected_amount,
                                                  product.ignored_by_productivity or 0)
    local productivity_base = expected_amount - productivity_base_complement
    local amount = (productivity_base_complement + productivity_base * productivity)
                   / recipe_duration

### Where we match

- Recipe duration formula (`recipe.energy / entity.crafting_speed`).
- Productivity cap is per-recipe (`recipe.maximum_productivity`),
  defaulting to the engine's +300%.
- Per-product expected-amount formula, including
  `extra_count_fraction`, probability, and `ignored_by_productivity`.
- Productivity does not affect ingredient consumption (mod multiplies
  ingredient amount by `1 / recipe_duration` only).
- Pollution uses `recipe.emissions_multiplier` * `(1 + pollution_bonus)`
  (we currently don't read `recipe.emissions_multiplier`; in 2.0+ it is
  almost always 1.0, but this is a known divergence -- see below).

### Where we extend

- **Quality cascade output distribution.** RateCalculator surfaces only
  the per-craft chance; we redistribute output across the quality
  ladder using the engine's documented `0.1` sub-cascade probability.
- **Beacon math from prototype data.** RateCalculator queries the live
  `entity.speed_bonus` etc., bypassing the beacon profile entirely; we
  rebuild it from `beacons.json` so users can plan layouts without
  pasting them first.
- **Per-recipe productivity research as input.** RateCalculator reads
  `recipe.productivity_bonus` off the live force; we accept the level
  explicitly.
- **Diagnostics.** We emit named warnings for every clamp / floor /
  cap, so the harness can flag dubious configurations.

### Where we diverge

- **Recipe `emissions_multiplier`.** Vanilla recipes leave this at 1.0;
  modded recipes (notably some Space Age recipes) override it. Our
  pollution math currently ignores the per-recipe multiplier. Fix: pull
  `emissions_multiplier` from the recipe row and fold into
  `pollution_per_min`. Marked as TODO in the source.
- **Beacon `same_type` counter.** RateCalculator iterates the actual
  beacons placed in-game; we trust the caller's `Beacon.count`. For a
  "12 beacons of one prototype" layout the math is identical; for
  mixed-prototype beacon clusters the caller should split into one
  `Beacon` per prototype.
- **Burner machines.** RateCalculator computes `burns_per_second`
  exactly from the fuel's `fuel_value` and the machine's
  `max_energy_usage * (1 + consumption_bonus)`. We currently report
  the machine's electric-equivalent power and ignore burner fuel rate.
  The harness's planner already emits a `fuel` field per cell; future
  work: add `inputs[fuel_name]` to the rate output for burner machines.

## API quick reference

```python
from tools.rate_calculator import RateInput, Beacon, compute_rates

inp = RateInput(
    recipe="electronic-circuit",
    machine="assembling-machine-3",
    machine_quality="normal",
    modules=[("productivity-module-3", "normal")] * 4,
    beacons=[
        Beacon(name="beacon", quality="normal", count=8,
               modules=[("speed-module-3", "normal")] * 2),
    ],
    research_levels={
        "change-recipe-productivity": {"electronic-circuit": 5},
    },
    machine_count=10,
)
out = compute_rates(inp)
print(out.crafts_per_second_total)
print(out.outputs_per_second)
print(out.power_kw_total)
for d in out.diagnostics:
    print("warn:", d)
```
