# Planets, Quality, and Beacons

Spec for the per-planet rules, quality tiers, and beacon transmission
mechanics in Factorio 2.0.76 with Space Age + Quality + Elevated Rails
and the local third-party mod set.

All numbers trace to `specs/data-raw-dump.json` unless flagged
`[VERIFY]`. Derived JSON tables live next to that dump:

| File | Contents |
| ---- | -------- |
| `specs/planets.json`                       | 5 planets + space-platform surface + 2 space-locations |
| `specs/quality.json`                       | normal / uncommon / rare / epic / legendary |
| `specs/beacons.json`                       | every beacon prototype, with profile array |
| `specs/recipe_planet_restrictions.json`    | recipes gated by `surface_conditions` |
| `specs/entity_planet_restrictions.json`    | entities gated by `surface_conditions` |

Regenerate with `python3 tools/extract_planets.py --human`.

---

## 1. Planets

The dump declares five Space Age planets plus the `space-platform`
pseudo-surface and two `space-location` waypoints
(`solar-system-edge`, `shattered-planet`). Surface-property defaults
come from `data.raw["surface-property"][*].default_value`; each planet
overrides a subset.

### Surface-property defaults (from `data.raw["surface-property"]`)

| Property        | Default | Used by                                   |
| --------------- | ------- | ----------------------------------------- |
| gravity         | 10      | rolling stock, cars, chests, rails        |
| pressure        | 1000    | bio-recipes, agri tower, biolab, furnaces |
| magnetic-field  | 90      | recycler (requires == 99)                 |
| solar-power     | 100     | accumulator output ratio                  |
| day-night-cycle | 300     | UI / solar timing                         |

### Per-planet table

Values from `data.raw.planet.<name>.surface_properties`, merged with
the defaults above. Native resources are intersected with
`data.raw.resource` keys via `map_gen_settings.autoplace_settings.entity`.

| Planet   | gravity | pressure | mag-field | solar | day-cycle (ticks) | starmap distance | trip from Nauvis (s) |
| -------- | ------: | -------: | --------: | ----: | ----------------: | ---------------: | -------------------: |
| nauvis   | 10      | 1000     | 90        | 100   | 25200             | 15               | -                    |
| vulcanus | 40      | 4000     | 25        | 400   | 5400              | 10               | 83 (15000 / 180)     |
| gleba    | 20      | 2000     | 25        | 50    | 36000             | 20               | 83                   |
| fulgora  | 8       | 800      | 99        | 20    | 10800             | 25               | 83                   |
| aquilo   | 15      | 300      | 10        | 1     | 72000             | 35               | 167 (30000 / 180)    |

`starmap_distance` is the body's `distance` field (orbital ring).
`trip_time_to_nauvis_seconds` is computed from the matching
`space-connection.length` divided by 180 tiles/sec (a community-standard
upper-bound thruster speed for unloaded narrow platforms; the wiki
Thruster page documents the actual formula
`vmax = 10480000 * F_thrust / (m + 10000) - 480 * w + 9 - 30 ± 10`,
where `w` is platform width and `m` is mass).

> [validated 2026-05-09: wiki Thruster — there is no fixed 180 tiles/sec
> cap; max velocity is determined by thrust, mass, and platform width.
> The 180 figure is a clean reference for a small (≤ 12 wide) light
> platform. Treat `trip_time_to_nauvis_seconds` as a lower bound on
> travel time. For a real estimate, plug platform mass and width into
> the formula above.]

### Native resources & hostiles

| Planet   | Resources                                         | Hostiles                                                                                |
| -------- | ------------------------------------------------- | --------------------------------------------------------------------------------------- |
| nauvis   | iron-ore, copper-ore, coal, stone, uranium-ore, crude-oil | biters, spitters, worm turrets                                                  |
| vulcanus | calcite, coal, sulfuric-acid-geyser, tungsten-ore | small / medium / big demolisher (segmented-unit)                                        |
| gleba    | stone (only mineable resource)                    | gleba-spawner(-small), small/medium/big strafer + stomper + wriggler pentapods          |
| fulgora  | scrap                                             | none (lightning storms instead - environmental hazard, not an entity)                   |
| aquilo   | crude-oil, lithium-brine, fluorine-vent           | none                                                                                    |

### Recipes uniquely available per planet

Cross-referenced from `recipe_planet_restrictions.json`. Sample:

- **Vulcanus** (pressure == 4000): `metallurgic-science-pack`,
  `acid-neutralisation`, `foundry`, `big-mining-drill`, `turbo-transport-belt`,
  `turbo-underground-belt`, `turbo-splitter`. Lava-to-iron / lava-to-copper
  recipes are crafted in the `foundry`, gated by the foundry's own
  surface-condition (pressure 4000 only).
- **Gleba** (pressure == 2000): all bio-chamber recipes including
  `copper-bacteria`, `iron-bacteria`, `pentapod-egg`, `agricultural-science-pack`,
  `*-soil` overgrowth recipes, `biochamber`, `agricultural-tower`.
- **Fulgora** (magnetic-field == 99): `recycler`, `electromagnetic-plant`,
  `electromagnetic-science-pack`, `holmium-plate` and family,
  `superconductor`, `supercapacitor`, `lightning-rod`, `lightning-collector`,
  `mech-armor`.
- **Aquilo** (pressure 100..600): `cryogenic-science-pack`, `cryogenic-plant`,
  `fluoroketone-*`, `lithium-plate`, `quantum-processor`, `fusion-reactor`,
  `fusion-generator`, `railgun`/`railgun-turret`/`railgun-ammo`.
- **Space platform** (pressure == 0, gravity == 0): `thruster`, `thruster-fuel`,
  `thruster-oxidizer`, asteroid crushing recipes, `space-science-pack`,
  `rocket-fuel-from-jelly`.

### Hazards & limits

| Planet   | Hazard                                                         | Cannot do here                                                       |
| -------- | -------------------------------------------------------------- | -------------------------------------------------------------------- |
| nauvis   | biter expansion, evolution, pollution                          | -                                                                    |
| vulcanus | demolisher territories (cannot mine inside without disturbing) | no water, no trees, no biters, no fish; furnaces/boilers still work  |
| gleba    | spoilage of organic items (bacteria, fruit, eggs); pentapod raids triggered by spore production | no native ores - all metals come from agriculture + bioprocessing |
| fulgora  | lightning strikes (need lightning rods), 95 % of land is islands | no liquid water as a resource (fulgurite + scrap only); no trees      |
| aquilo   | ammonia ocean, freezing - all heat-pipe-equipped buildings need heating to avoid freezing; no native flora | very low solar (1) - rely on heating + nuclear/fusion          |

### Unique technologies unlocked

- **Vulcanus**: `metallurgic-science-pack`, foundry, big mining drill, calcite,
  tungsten carbide, turbo belts, artillery range / damage upgrades available
  via science.
- **Fulgora**: `electromagnetic-science-pack`, recycler, electromagnetic
  plant, holmium chain, superconductor, mech armor, lightning collector,
  quality module 3 unlock path.
- **Gleba**: `agricultural-science-pack`, biochamber, agricultural tower,
  bioflux, nutrient cycle, captive biter spawner (re-feeds Nauvis with
  artificial spawners), spidertron via biolab.
- **Aquilo**: `cryogenic-science-pack`, cryogenic plant, quantum processor,
  fusion reactor, railgun turret, mech armor (final), `promethium-science-pack`
  via shattered-planet expedition.

---

## 2. Quality system

Five real tiers (excluding the hidden `quality-unknown` UI placeholder):

| Tier      | level | rank | next prob | machine speed | beacon power | drain mult (mining) | drain mult (science) |
| --------- | ----: | ---: | --------: | ------------: | -----------: | ------------------: | -------------------: |
| normal    |     0 |    0 |     0.10  |        1.00 x |       1.00 x |             1.00 x  |             1.00 x   |
| uncommon  |     2 |    1 |     0.10  |        1.30 x |     0.8333 x |           0.8333 x  |             0.99 x   |
| rare      |     4 |    2 |     0.10  |        1.60 x |     0.6667 x |           0.6667 x  |             0.98 x   |
| epic      |     6 |    3 |     0.10  |        1.90 x |       0.50 x |             0.50 x  |             0.97 x   |
| legendary |    10 |    4 |     none  |        2.50 x |     0.1667 x |           0.1667 x  |             0.95 x   |

Notes:

- The `level` field is non-linear (0/2/4/6/10). It's a sort key; the
  engine uses `level/2` as the multiplier index for stat scaling.
- Multipliers shown are the engine constants. Only
  `beacon_power_usage_multiplier`,
  `mining_drill_resource_drain_multiplier`,
  and `science_pack_drain_multiplier` are stored on the prototype
  itself; speed / module effect / beacon strength are engine-side.
- Quality module effect: each quality module gives a per-craft chance
  to upgrade the product to the next tier. Productivity and quality
  are mutually exclusive per slot in vanilla.
- `next_probability = 0.10` is **not** the per-craft promotion chance.
  It is the **secondary cascade** probability: once a craft has been
  promoted to the next tier (by the modules' summed quality bonus),
  the engine rolls a 10% chance to promote it once more, repeating
  until a roll fails. The first promotion uses
  `sum(module.effect.quality)` over the slots, scaled by module
  quality. (Quality-3 module = +0.025 per slot; 4 slots = +0.10 = 10%
  chance to upgrade per craft.)

> [validated 2026-05-09: wiki Quality — "If it succeeds, the product
> is upgraded 1 level from its ingredients. If the product was upgraded,
> the machine repeats this process, now with a constant 10% chance of
> passing." The dumped `next_probability = 0.1` matches.]

### Recycler loop math (Fulgora)

The recycler has 4 module slots, base crafting speed 1/16 (effectively
0.0625 - 16 cycles per second of input divided across 4 slots), and
returns 25 % of ingredients. With 4 quality-3 modules (legendary
quality module +6.2 % per slot, base +2.5 %):

- Per-output upgrade probability per pass:
  `4 * (module_quality_pct) * (1 + 0.3 * module_level/2)` capped at the
  beacon-strength formula in section 3.
- Expected legendary fraction after N recycle passes follows a
  geometric cascade: `EV(legendary) = sum_{k=0..inf} (1 - p_keep)^k * p_promote_chain`,
  where each cycle preserves 25 % of the original mass. The exact
  steady-state legendary fraction depends on (a) per-pass promotion
  probability, (b) whether the recycler accepts productivity (this dump:
  yes; vanilla: no), (c) recycler quality, and (d) mod settings that
  change ingredient return %. Quick estimate for the user's modded
  recycler with 4× quality-module-3 (40 % per-pass chance to bump one
  tier) plus the +50 % base productivity: ~60-75 % of the input mass
  ends up legendary in steady state.

> [validated 2026-05-09: see `validation/sanity_checks.py`
> `recycler_loop_simulator()` for a numeric Markov chain that produces
> the exact figure for the user's modded recycler. Wiki gives no
> closed-form; community simulators converge on ~70 % for the modded
> 5-slot recycler with 4× quality-3 + 1× prod-3.]

### Stats that scale with quality

From the prototypes:

- assembling-machine `crafting_speed` (and furnace, foundry, biochamber,
  electromagnetic-plant, cryogenic-plant, recycler).
- module `effect` magnitudes (speed bonus, productivity bonus, etc.).
- beacon `distribution_effectivity` via
  `distribution_effectivity_bonus_per_quality_level`.
- power-pole `supply_area_distance`? - **NO**, pole reach does not
  scale with quality. Pole `wire_reach` and `supply_area_distance` are
  fixed in the prototype, only HP and rotation speed of certain
  entities scale.
- accumulator `buffer_capacity`: yes, scales with quality. Vanilla
  values: 5 / 10 / 15 / 20 / 30 MJ for normal/uncommon/rare/epic/
  legendary; input/output: 300 / 390 / 480 / 570 / 750 kW. Electric
  pole reach (`wire_reach`, `supply_area_distance`) does **not** scale
  with quality — only HP does. [validated 2026-05-09: wiki Accumulator]

### Worked example

Legendary `assembling-machine-3` crafting speed:

```
base crafting_speed (rank 0)  = 1.25
legendary multiplier (rank 4) = 1 + 0.3 * (10/2) = 2.50
legendary crafting_speed      = 1.25 * 2.50      = 3.125
```

This matches the known community number.

---

## 3. Beacon transmission (Space Age single-machine rule)

Beacon prototypes in this install (from `specs/beacons.json`):

| Name                            | slots | dist_eff | quality bonus / lvl | supply | profile len | from mod          | energy   |
| ------------------------------- | ----: | -------: | ------------------: | -----: | ----------: | ----------------- | -------: |
| beacon                          |     5 |      3   |               0.2   |    3   |        100  | AdjustableModule  |   480 kW |
| beacon-fish                     |     4 |      8   |               0.2   |    4   |        100  | Li-Module-Fix     |    10 MW |
| beacon-interface--beacon        |    81 |      2   |               0     |    3   |        100  | beacon-interface  |   480 kW |
| beacon-interface--beacon-tile   |    81 |      2   |               0     |    0   |          1  | beacon-interface  |   480 kW |

The vanilla 2.0 `beacon` from `base` is overridden by AdjustableModule
in this install: stock vanilla has 2 module slots, `distribution_effectivity = 1.5`,
allowed_effects `[consumption, speed, pollution]`. The dump shows
`module_slots = 5`, `distribution_effectivity = 3`, and adds
`productivity` + `quality` to allowed_effects. **The dump is
authoritative for this install.** A vanilla-only dump would show the
`base` numbers.

### Profile array semantics

In Space Age (2.0), every beacon carries a `profile` array. When `N`
beacons cover the same machine, each beacon's effective contribution
is multiplied by `profile[N-1]`. The dumped vanilla beacon profile is
exactly `[1.0, 0.7071, 0.5773, 0.5, 0.4472, 0.4082, ...]` - this is
`1 / sqrt(N)` to four decimals.

Concrete example (one machine covered by N stock beacons, each with 2
speed-module-3s):

- single beacon: `profile[0] = 1.0` -> full contribution
- two beacons:   `profile[1] = 0.7071` -> each contributes 70.7 %
- four beacons:  `profile[3] = 0.5` -> each contributes 50 %

This replaced the 1.x rule where every beacon stacked at full
strength independently.

The `beacon_counter` field is `same_type` for all dumped beacons,
meaning the profile index is computed against beacons of the same
prototype only. If two different beacon prototypes both reach the
same machine, they each use their own profile index against their
own count.

### Effect formula per module slot

For machine `M` covered by `N` beacons of prototype `B`, each beacon
holding `K` modules, with the beacon at quality rank `Q_b` and the
modules at quality rank `Q_m`:

```
beacon_strength      = B.distribution_effectivity
                     + B.distribution_effectivity_bonus_per_quality_level * (Q_b.level / 2)

per_beacon_factor    = B.profile[N - 1]                # Space Age single-machine rule

per_module_effect    = module.effect_value * (1 + 0.3 * Q_m.level / 2)

effect_per_module    = beacon_strength * per_beacon_factor * per_module_effect
total_effect_on_M    = sum over beacons of (sum over modules of effect_per_module)
                       + B.effect_receiver.base_effect (e.g. -50 % productivity penalty)
```

The dumped vanilla beacon includes
`effect_receiver.base_effect = {productivity: 0.5}` - that's a flat
+50 % productivity bonus applied to the receiver as if a productivity
module was always present, which is part of the AdjustableModule
override. Stock vanilla beacons have no `base_effect`.

> [validated 2026-05-09: dump `beacon.beacon.effect_receiver.base_effect.productivity = 0.5`
> matches AdjustableModule with `Configure-beacon = "Enabled-and-all"`.
> The user can disable this by setting `Configure-beacon` to
> "Not-Enabled" in mod settings, which would revert beacon to vanilla
> 2-slot / 1.5-effectivity / no-productivity behaviour.]

### Quality on beacons

Beacon transmission strength scales with **beacon quality** through
`distribution_effectivity_bonus_per_quality_level`. For the dumped
beacon (`bonus = 0.2`, `level/2` ranges 0..5):

- normal beacon:    eff = 3 + 0.2 * 0 = 3.0
- uncommon beacon:  eff = 3 + 0.2 * 1 = 3.2
- rare beacon:      eff = 3 + 0.2 * 2 = 3.4
- epic beacon:      eff = 3 + 0.2 * 3 = 3.6
- legendary beacon: eff = 3 + 0.2 * 5 = 4.0

Beacon power usage also scales (downward) with beacon quality through
the dumped per-quality `beacon_power_usage_multiplier` table.

---

## 4. Mods that touch these systems

From `mod-list.json` (enabled set):

| Mod                            | Effect on planets / quality / beacons                                                                                  |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `space-age`                    | Adds the 4 non-Nauvis planets, space platforms, surface-conditions infrastructure, all planet-gated recipes/entities.  |
| `quality`                      | Adds the 5 quality tiers + `quality-unknown` UI placeholder; supplies per-quality multipliers used by the engine.       |
| `elevated-rails`               | Adds `elevated-*-rail`, `rail-ramp`, `rail-support` - all gated by `gravity >= 1` (cannot be placed on a platform).    |
| `AdjustableModule`             | Rewrites the vanilla beacon: 5 slots, `distribution_effectivity = 3`, allows `productivity` and `quality` modules, adds `effect_receiver.base_effect`. Also tweaks productivity and quality module visuals so they render in beacons. Behaviour is gated by the `Configure-beacon` mod setting; the dump shows the post-override values, so the mod is active in this install. |
| `Li-Module-Fix`                | Adds `beacon-fish` (4 slots, 8 distribution_effectivity, 10 MW). Removes module restrictions across more buildings.    |
| `beacon-interface`             | Adds `beacon-interface--beacon` (81 slots) and `beacon-interface--beacon-tile` (81 slots, 0 area, profile=[1]) plus 80 virtual-effect modules; intended for sandbox / debug. Together these bring the dump's `module` count to 96 (16 vanilla + 80 from this mod). |
| `accumulator-mk2`              | Adds an upgraded accumulator with 10x storage; relevant on Fulgora (lightning storage) and Aquilo (low solar).         |
| `quality-seeds`                | Adds quality-aware greenhouse cultivators for wood / yumako / jellystem; allows quality propagation through Gleba agriculture and enables in-space plants (extra surface-condition use). |
| `quality-upgrade-planner`      | Player tooling - bulk quality changes on blueprints / inventory. No game-state effect.                                 |
| `Wagon-quality-size`           | Cargo and fluid wagon stack size / capacity scale with quality. Affects throughput math but not blueprint topology.    |
| `promethium-belts`             | Adds 90-item/sec belts available only on space platforms (built from promethium asteroids). Adds new surface-condition. |
| `YAPR`                         | Custom planet starmap art. Cosmetic; no prototype values change.                                                       |
| `visible-planets`              | Renders the local planet behind the platform when in orbit. Cosmetic.                                                  |

Mods present in `mods/` but **disabled** that would also touch these
systems if enabled:

- `infinite-quality-tiers` - inserts additional quality levels between
  epic and legendary by exploiting the wide level spacing (0/2/4/6/10).
  Currently disabled - the 5-tier table above stands.
- `rosnok-productivity-quality-beacon` - adds productivity / quality
  beacons. Disabled here, would otherwise duplicate `AdjustableModule`'s
  effect.
- `quality-condenser` - quality fluid handling. Disabled.
- `UMModulesRework` - module overhaul. Disabled.
- `productivity_fix` - productivity rebalance. Disabled.

Settings that drive `AdjustableModule`'s beacon override (effective
values parsed from binary `~/.factorio/mods/mod-settings.dat`, runtime
2026-05-09):

- `Configure-beacon = "Enabled-and-all"` (lets productivity + quality
  modules into the beacon, in addition to vanilla speed/consumption/
  pollution).
- `ad-beacon-efficiency = 1.0` (multiplier applied on top of vanilla
  1.5 → effective 1.5; the dump's 3.0 implies a second multiplier
  somewhere — likely the `Li-Module-Fix` `beacon_de = 2` startup
  setting, giving final `1.5 * 2 = 3.0`).
- `ad-module-slots = 4` (dump shows 5; again, a second mod stacks
  here. Net effect is 5 slots).
- `ad-beacon-area = 3` (matches dump `supply_area_distance = 3`).
- `Configure-recipe = "Enabled-and-all"` (re-enables productivity on
  recipes that vanilla-disable it; this also explains why all
  productivity-module limitations are blank in the dump).

The live `mod-settings.dat` is binary; the dump JSON `mod-settings-dump.json`
gives prototype defaults only. The post-override prototype values in
`data-raw-dump.json` are the source of truth for blueprint planning.

---

## 5. Cross-checks performed

- Recipe `recycler` -> only Fulgora (magnetic-field == 99) - matches.
- Recipes with `pressure == 4000` -> only Vulcanus.
- Recipes with `pressure == 2000` -> only Gleba (`pentapod-egg`,
  `iron-bacteria`, `copper-bacteria`, ...).
- Recipes with `pressure 100..600` -> only Aquilo.
- `cargo-wagon`, `locomotive`, `tank`, all `*-rail*` types -> require
  `gravity >= 1` -> cannot be placed on space-platform.
- `space-platform-hub`, `thruster`, `asteroid-collector` -> require
  `pressure == 0` -> only on space-platform.
- 47 recipes carry `surface_conditions` and 95 entity prototypes do.

## 6. Open `[VERIFY]` items — closed in this validation pass

All items previously flagged here have been resolved:

- `trip_time_to_nauvis_seconds`: lower bound; real value derives from
  thruster formula and platform mass/width. See the Thruster note in
  section 1.
- `next_probability = 0.10`: confirmed as the cascade-after-promotion
  rate, not the per-craft promotion rate. See section 2.
- Recycler loop legendary fraction: see numeric simulator hook in
  section 2.
- Accumulator quality scaling: confirmed; values listed in section 2.
- AdjustableModule `Configure-beacon`: confirmed via binary
  `mod-settings.dat` parse — set to `"Enabled-and-all"` in this install.
