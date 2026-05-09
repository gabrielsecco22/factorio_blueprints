# Machines and Recipes

Authoritative reference for the crafting model used by the toolkit. All values
are derived from `specs/data-raw-dump.json` via `tools/extract_machines.py`
and saved to `specs/{machines,recipes,recipe_categories,items,fluids,modules}.json`.

This dump reflects the user's actual mod set: Factorio 2.0.76 + Space Age +
Quality + Elevated Rails + roughly 30 additional mods. Where vanilla and the
dump disagree, the dump wins.

## 1. Catalogs

| File | Count (this dump) | Source prototype types |
| --- | --- | --- |
| `specs/machines.json` | 40 | assembling-machine, furnace, rocket-silo, mining-drill, boiler, generator, reactor, fusion-generator, fusion-reactor, agricultural-tower, asteroid-collector, lab, beacon |
| `specs/recipes.json` | 717 | recipe |
| `specs/recipe_categories.json` | 33 crafting + 4 resource | computed cross-table |
| `specs/items.json` | 448 | item, tool, module, ammo, capsule, armor, gun, repair-tool, rail-planner, space-platform-starter-pack, item-with-entity-data, selection-tool, spidertron-remote |
| `specs/fluids.json` | 34 | fluid |
| `specs/modules.json` | 16 | module (beacon-interface placeholders excluded) |

Re-run extraction after a dump refresh:

```
python3 tools/extract_machines.py
```

The script is stdlib-only.

## 2. Machine taxonomy

### Crafting machines (consume a recipe)

| Machine | Type | Speed | Slots | Base prod. | Footprint | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| stone-furnace | furnace | 1.0 | 1 (vanilla 0) | +50% (vanilla 0%) | 2x2 | smelting only; burner (chemical) |
| steel-furnace | furnace | 2.0 | 1 (vanilla 0) | +50% (vanilla 0%) | 2x2 | smelting only; burner (chemical) |
| electric-furnace | furnace | 2.0 | 3 (vanilla 2) | +50% (vanilla 0%) | 3x3 | smelting only; electric |
| recycler | furnace | 0.5 | 5 (vanilla 4) | +50% (vanilla 0%, vanilla disallows productivity entirely) | 1.4x3.4 -> 2x4 tile | recycling only; magnetic-field >= 99 |
| assembling-machine-1 | assembling-machine | 0.5 | 1 (vanilla 0) | +50% (vanilla 0%) | 3x3 | basic-crafting/crafting only |
| assembling-machine-2 | assembling-machine | 0.75 | 3 (vanilla 2) | +50% (vanilla 0%) | 3x3 | adds fluid recipes |
| assembling-machine-3 | assembling-machine | 1.25 | 5 (vanilla 4) | +50% (vanilla 0%) | 3x3 | adds metallurgy/electronics-or-assembling fallbacks |
| oil-refinery | assembling-machine | 1.0 | 4 (vanilla 3) | +50% (vanilla 0%) | 5x5 | oil-processing |
| chemical-plant | assembling-machine | 1.0 | 4 (vanilla 3) | +50% (vanilla 0%) | 3x3 | chemistry / chemistry-or-cryogenics |
| centrifuge | assembling-machine | 1.0 | 3 (vanilla 2) | +50% (vanilla 0%) | 3x3 | centrifuging |
| crusher | assembling-machine | 1.0 | 3 (vanilla 2) | +50% (vanilla 0%) | 3x2 | crushing (asteroids, scrap precursor) |
| foundry | assembling-machine | 4.0 | 5 (vanilla 4) | +100% (vanilla +50%) | 5x5 | metallurgy + pressing; electric |
| electromagnetic-plant | assembling-machine | 2.0 | 6 (vanilla 5) | +100% (vanilla +50%) | 4x4 | electromagnetics + electronics |
| biochamber | assembling-machine | 2.0 | 5 (vanilla 4) | +100% (vanilla +50%) | 3x3 | organic; **burner using nutrients**, negative pollution |
| cryogenic-plant | assembling-machine | 2.0 | 9 (vanilla 8) | +50% (vanilla 0%) | 5x5 | cryogenics; chemistry-or-cryogenics |
| captive-biter-spawner | assembling-machine | 1.0 | 1 | +50% | 3x3 | captive-spawner-process; consumes pentapod-egg |
| jellystem-greenhouse | assembling-machine | 2.0 | 5 | none | 3x3 | cultivation-jellystem (mod: quality-seeds) |
| yumako-tree-greenhouse | assembling-machine | 2.0 | 5 | none | 3x3 | cultivation-yumako-tree (mod: quality-seeds) |
| tree-plant-greenhouse | assembling-machine | 2.0 | 5 | none | 3x3 | cultivation-tree-plant (mod: quality-seeds) |
| space-cultivator | assembling-machine | 2.0 | 5 | +100% | 3x3 | space-cultivation (mod: quality-seeds) |
| spore-tower | furnace | 1.0 | 5 | +50% | 3x3 | spore-releasing (mod: quality-seeds) |
| rocket-silo | rocket-silo | 1.0 | 5 | +50% | 9x9 | rocket-building; uses `rocket_parts_required` parts before launch |
| biolab | lab | n/a | 5 | +50% | 4x4 | researches science packs (mod-extended `lab`) |
| lab | lab | n/a | 3 | +50% | 3x3 | researches science packs |

### Producers (no recipe; consume environment / produce energy)

| Machine | Type | Slots | Notes |
| --- | --- | --- | --- |
| burner-mining-drill | mining-drill | 1 | basic-solid; burner; 0.25 mining_speed (vanilla) |
| electric-mining-drill | mining-drill | 4 | basic-solid; 0.5 mining_speed |
| pumpjack | mining-drill | 3 | extracts crude-oil |
| big-mining-drill | mining-drill | 5 | basic-solid + hard-solid; 2.5 mining_speed (Space Age) |
| boiler | boiler | 0 | water -> steam@165 (1.8 MW) |
| heat-exchanger | boiler | 0 | water -> steam@500 |
| steam-engine | generator | 0 | 0.5 fluid/tick @ 165 -> 900 kW |
| steam-turbine | generator | 0 | high-temp steam -> 5.82 MW |
| nuclear-reactor | reactor | 0 | 40 MW base; neighbour bonus |
| heating-tower | reactor | 0 | burner -> heat (Aquilo) |
| fusion-reactor | fusion-reactor | 0 | produces plasma from fusion-power-cell |
| fusion-generator | fusion-generator | 0 | plasma -> electricity |
| asteroid-collector | asteroid-collector | 0 | grabs asteroids in space |
| agricultural-tower | agricultural-tower | 0 | plants & harvests crops |

### Beacons

| Beacon | Slots | Distribution | Supply area |
| --- | --- | --- | --- |
| beacon | 5 (vanilla 2) | 3.0 (vanilla 1.5) | 3 (same as vanilla) |
| beacon-fish | 4 | (mod, cheat variant) | n/a |

> [validated 2026-05-09: wiki Beacon — vanilla 2.0 = 2 slots, 1.5
> distribution_effectivity, 9x9 supply area, 480 kW base power, allowed
> effects = `[consumption, speed, pollution]` only (no productivity, no
> quality). Dump shows 5 / 3.0 / 3 supply distance / `consumption, speed,
> productivity, pollution, quality` allowed; the beacon was rewritten by
> the `AdjustableModule` mod (effective `mod-settings.dat` confirms
> `Configure-beacon = "Enabled-and-all"` and `ad-module-slots = 4`,
> with `ad-beacon-area = 3`). The +50 % `effect_receiver.base_effect.productivity`
> is also a mod addition; vanilla beacons have no `base_effect`.]
> Treat `specs/beacons.json` as the truth for this user; for cross-save
> portability use the `vanilla_2_0_76` annotations.

## 3. The crafting math

The number of items a single machine produces per second on a recipe is:

```
items_per_second_per_machine =
    (machine.crafting_speed * quality_speed_mult * (1 + sum(speed_effects)))
    / recipe.energy_required
    * (1 + min(maximum_productivity, sum(productivity_effects)))
    * results.amount * results.probability
```

Where `sum(speed_effects)` and `sum(productivity_effects)` add together:

- Each module slot's module effect (after the machine's `allowed_effects` filter).
- Beacon effects: `beacon.distribution_effectivity * sum_over_modules(effect)`,
  applied per beacon, summed over all beacons in supply range.
- The machine's own `effect_receiver.base_effect` (foundry +100% productivity,
  EM-plant +100%, biochamber +100%, almost everything else +50% in this dump).
- Surface effects (Gleba spawners etc.) when `uses_surface_effects` is true.

`(1 + sum_speed)` is clamped to a minimum of `0.2` (a machine never goes below
20% of its base speed regardless of negative speed modifiers).

### Quality speed multiplier on machines

Pulled from `data.raw.quality.*`:

| Quality | level | beacon power mult | mining drill drain mult |
| --- | --- | --- | --- |
| normal | 0 | 1.000 | 1.000 |
| uncommon | 2 | 0.833 | 0.833 |
| rare | 4 | 0.667 | 0.667 |
| epic | 6 | 0.500 | 0.500 |
| legendary | 10 | 0.167 | 0.167 |

> [validated 2026-05-09: wiki Quality + Assembling_machine_3 — vanilla
> 2.0 + Quality DLC scales `crafting_speed` by `1 / 1.3 / 1.6 / 1.9 /
> 2.5` (normal, uncommon, rare, epic, legendary). The dump's
> `data.raw.quality.<tier>` only stores `beacon_power_usage_multiplier`,
> `mining_drill_resource_drain_multiplier`, and
> `science_pack_drain_multiplier`; the speed multiplier is engine-derived
> from `level/2 * 0.3 + 1` (at level 10 = legendary the multiplier
> becomes 2.5, not 2.5 = 1 + 5*0.3 → 2.5 confirms). Treat these as
> hard-coded engine constants. The same multiplier applies to module
> effect magnitudes and to beacon-strength-bonus per quality.]

### Productivity cap

Each recipe can carry a `maximum_productivity` field (Factorio 2.0 added the
"productivity research" tier that pushes recipes up to +300%). When unset,
treat as `+300%` (`3.0`). Productivity effects from beacons / modules /
research / base_effect all add into a single bonus that is then clamped:

```
applied_productivity = min(maximum_productivity ?? 3.0, raw_productivity_sum)
```

Recipes with `allow_productivity == false` (e.g. raw smelting in mod-free
vanilla, parameter recipes, item-recycling for base ores) reject all
productivity contributions. Modules whose `effect.productivity > 0` cannot be
inserted into machines that do not list `productivity` in `allowed_effects`.

### Crafting-categories cross-table

`specs/recipe_categories.json` is the canonical lookup. Highlights for this
dump:

| Category | Machines |
| --- | --- |
| crafting | assembling-machine-1/2/3 |
| basic-crafting | assembling-machine-1/2/3 |
| advanced-crafting | assembling-machine-2/3 |
| crafting-with-fluid | assembling-machine-2/3 |
| smelting | stone-furnace, steel-furnace, electric-furnace |
| chemistry | chemical-plant, cryogenic-plant (via chemistry-or-cryogenics) |
| oil-processing | oil-refinery |
| centrifuging | centrifuge |
| rocket-building | rocket-silo |
| recycling | recycler |
| metallurgy | foundry |
| electromagnetics | electromagnetic-plant |
| organic | biochamber |
| cryogenics | cryogenic-plant |
| pressing | foundry, assembling-machine-3 |
| crushing | crusher |
| captive-spawner-process | captive-biter-spawner |
| spore-releasing | spore-tower |
| cultivation-jellystem / cultivation-yumako-tree / cultivation-tree-plant | matching greenhouse |
| space-cultivation | space-cultivator |

The "or-..." compound categories (`metallurgy-or-assembling`,
`organic-or-chemistry`, etc.) exist so a single recipe can fall back to a
weaker machine when a specialist isn't unlocked. They show up directly in
each machine's `crafting_categories` and need no special handling beyond the
intersect-with-recipe-category lookup.

## 4. Modules

Vanilla module set in this dump:

| Module | Category | Tier | Effect |
| --- | --- | --- | --- |
| speed-module / -2 / -3 | speed | 1/2/3 | +20%/+30%/+50% speed; +50%/+60%/+70% consumption; -10%/-15%/-25% quality |
| efficiency-module / -2 / -3 | efficiency | 1/2/3 | -30%/-40%/-50% consumption |
| productivity-module / -2 / -3 | productivity | 1/2/3 | +4%/+6%/+10% productivity; +40%/+60%/+80% consumption; +5%/+7%/+10% pollution; -5%/-10%/-15% speed |
| quality-module / -2 / -3 | quality | 1/2/3 | +10%/+20%/+25% quality; -5% speed |

Quality-module values shown above are the **internal-fraction** values stored
in the prototype (`0.10`, `0.20`, `0.25`). The in-game tooltips translate
quality module 3 to `+2.5%` chance to upgrade quality per slot, because the
engine multiplies `effect.quality * 0.1` when summing.

> **[VERIFY]** This dump also exposes `*-module-fish` variants (e.g.
> `productivity-module-fish` gives +50% productivity, `quality-module-fish`
> gives `effect.quality = 5.0`). These appear to be cheat / debug items
> from a development-helper mod, not regular gameplay items. Filter them
> out of recommendation logic unless the user explicitly opts in.

### Module limitations

In this dump, no module sets `limitation` or `limitation_blacklist`, which
is unusual: vanilla productivity modules normally restrict themselves to
intermediate recipes. A mod has lifted the restriction. The toolkit should
**not** assume productivity modules are universally legal in every blueprint
recommendation - check the recipe's `allow_productivity` flag instead, which
is the engine's own gate.

## 5. Spoilage

`spoil_ticks` is in game ticks (60/sec). `spoil_result` is the item produced
when a stack expires; absent values mean the item is consumed silently
(e.g. biter-egg hatches a biter rather than spoiling into anything).

| Item | Lifetime | Spoils into |
| --- | --- | --- |
| copper-bacteria | 60 s | copper-ore |
| iron-bacteria | 60 s | iron-ore |
| yumako-mash | 3 min | spoilage |
| jelly | 4 min | spoilage |
| nutrients | 5 min | spoilage |
| pentapod-egg | 15 min | (hatches) |
| biter-egg / captive-biter-spawner | 30 min | (hatches) |
| yumako | 60 min | spoilage |
| jellynut | 60 min | spoilage |
| agricultural-science-pack | 60 min | spoilage |
| bioflux | 120 min | spoilage |
| raw-fish | ~125.8 min | spoilage |

For pipeline math: nutrient-fed biochambers must turn over their `nutrients`
buffer faster than 5 minutes, otherwise a chamber stalls when its fuel slot
spoils. When sizing a "nutrients-from-bioflux" loop, plan for the 2 h bioflux
shelf life as the upper bound.

## 6. Space Age machine quirks

- **biochamber** burns `nutrients` (a spoilable item) instead of being
  electric. Plan a constant nutrient supply line (1 nutrients lasts ~7s at
  full burn; check `energy_usage_kw=500` and `fuel_value_kj=2000`). Pollution
  is **negative** (-1 spores/min) - planting offsets pollution.
- **foundry** has `+100%` base productivity stamped in `effect_receiver`, so
  even bare foundries double their output. With four prod-3 modules and
  beacons, foundry recipes routinely hit the `maximum_productivity = 3.0`
  cap.
- **electromagnetic-plant** likewise +100%, six module slots, and the only
  source of `electromagnetics` recipes.
- **cryogenic-plant** has +50% base productivity and **nine** module slots;
  it accepts `chemistry-or-cryogenics` recipes too, so it's a faster
  chemical-plant once unlocked.
- **recycler** runs at `0.5 * 1/16 * <recipe>` cycles per second relative to
  the source recipe. Concretely: a `recipe.energy_required` of `3.2 s` for
  iron-plate becomes `0.2 s` for `iron-plate-recycling`; the recycler
  finishes that in `0.2 / 0.5 = 0.4 s`. Each cycle returns 25% of each
  ingredient (`probability: 0.25`). With four prod-3 modules and the +50%
  base productivity, the effective return cap is `min(1.0, 0.25 * (1 + 1.5
  + 4*0.10)) = 0.725` per ingredient - well under the 100% cap.
- **rocket-silo** uses `rocket_parts_required` rocket-parts before a launch.
  In this dump the silo has 5 module slots and accepts productivity, so
  rocket-part production scales with modules / beacons just like a normal
  assembler.

## 7. How to query the catalog

```python
import json, pathlib

specs = pathlib.Path("specs")
recipes = json.loads((specs / "recipes.json").read_text())
machines = json.loads((specs / "machines.json").read_text())
cats = json.loads((specs / "recipe_categories.json").read_text())

# Which machines can craft "advanced-circuit"?
recipe = next(r for r in recipes if r["name"] == "advanced-circuit")
candidates = cats["crafting_categories"].get(recipe["category"], [])
print(recipe["category"], "->", candidates)
```

For the "best machine for recipe X" decision, intersect the recipe's
category with `cats["crafting_categories"]`, then sort the candidates by
`crafting_speed * (1 + base_effect.productivity)`. Anything in the candidate
list with a higher `module_slots` count beats a lower-slot peer once you add
modules.

## 8. Mod-origin tagging

Each catalog record carries `from_mod`, derived heuristically from icon
asset paths (`__base__`, `__space-age__`, `__quality__`, `__elevated-rails__`,
or one of the 30-odd third-party mods). Where no icon is present, `from_mod`
is `null` - this is fine; it just means the prototype was either inherited
from a parent prototype or is mod data without a custom icon.

Mod prefixes seen in this dump include at least: `base`, `space-age`,
`quality`, `elevated-rails`, `quality-seeds`. Run

```
python3 -c "import json; print(sorted({m['from_mod'] for m in json.load(open('specs/machines.json'))}))"
```

to enumerate what is currently active.
