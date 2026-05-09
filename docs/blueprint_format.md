# Factorio 2.0 Blueprint String Format

Target: Factorio 2.0.76 + Space Age + Quality + Elevated Rails.
Authoritative source for the encoding pipeline: https://wiki.factorio.com/Blueprint_string_format
Cross-checked against `specs/data-raw-dump.json` (prototype data).
Binary library file `/home/gabriel/.factorio/blueprint-storage-2.dat` is the in-game storage; this spec covers only the export string format and is not for parsing that file.

Conventions:
- Types use TypeScript-ish notation: `string`, `number` (float64 unless noted), `int`, `bool`, `T[]`, `{...}`.
- `?` suffix = optional. `!` = required-when-present.
- All examples are valid JSON and round-trip through `tools/blueprint_codec.py`.

---

## 1. Encoding pipeline

A blueprint string is one ASCII line with no whitespace:

```
<version_byte><base64(zlib_deflate(utf8(json)))>
```

Step-by-step:
1. Build the JSON object (`{"blueprint": {...}}` or `{"blueprint-book": {...}}`, etc).
2. Serialise to compact UTF-8 JSON (no insignificant whitespace; game uses `,`/`:` separators).
3. zlib-compress with default deflate (RFC 1950 with `78 9C` or `78 DA` header; level 9 in practice).
4. base64-encode the deflated bytes using the **standard** alphabet (`A-Z a-z 0-9 + /` with `=` padding). NOT URL-safe.
5. Prepend a single ASCII version byte. Currently always `'0'` (0x30). Future format revisions would bump it.

Decoding is the inverse. Unknown leading bytes other than `'0'` should raise.

### 1.1 Worked example

Source object:

```json
{"blueprint":{"icons":[{"signal":{"name":"small-electric-pole"},"index":1}],"entities":[{"entity_number":1,"name":"small-electric-pole","position":{"x":0,"y":0}}],"item":"blueprint","version":562949954076673}}
```

Pipeline:
- UTF-8 length: 209 bytes.
- After zlib level-9: 148 bytes.
- After base64: 200 chars.
- Final string (201 chars including version byte):

```
0eNp9js0KwjAQhN9lzilU7Q/Nq4hIWxdZSDYlScVS8u4m9eDNy8AOM9/OjsmstHiWCL2DZycB+roj8FNGUzwZLUEj2NGYigzN0fNcLc4QkgLLg97Qp3RTIIkcmb6A49justqJfA6ofyCFxYXcdVI+Zl6tsGVNBcuRbO79hiq8yIcj3HbnoRmGtqn7rusvKX0AwFVGCg==
```

To reproduce: `tools/blueprint_codec.py decode '0eNp9js0KwjAQhN9lzilU7Q...'`.

---

## 2. Top-level wrapper

The decoded JSON has exactly one of four root keys:

| Root key                  | `item` field value         | Purpose                          |
| ------------------------- | -------------------------- | -------------------------------- |
| `blueprint`               | `"blueprint"`              | Single blueprint                 |
| `blueprint-book`          | `"blueprint-book"`         | Nested collection                |
| `deconstruction-planner`  | `"deconstruction-planner"` | Marks entities/tiles for removal |
| `upgrade-planner`         | `"upgrade-planner"`        | Maps entity A -> entity B        |

### 2.1 Common wrapper fields (all four)

| Field         | Type                   | Required | Notes                                                                                         |
| ------------- | ---------------------- | -------- | --------------------------------------------------------------------------------------------- |
| `item`        | `string`               | yes      | Always equal to the root key.                                                                 |
| `label`       | `string`               | no       | User-set name. May contain rich-text tags like `[item=iron-plate]`.                           |
| `label_color` | `{r,g,b,a}` floats 0-1 | no       |                                                                                               |
| `description` | `string`               | no       |                                                                                               |
| `icons`       | `Icon[]` (1-4)         | yes\*    | Required for `blueprint` / `blueprint-book`; optional otherwise. See 2.4.                     |
| `version`     | `int` (uint64)         | yes      | Packed game version. Layout: `(major<<48) | (minor<<32) | (patch<<16) | developer`. Example `562949954076673` = 2.0.10.1. For 2.0.76 use `(2<<48) | (76<<16) = 562949958402048`. |

### 2.2 `blueprint-book` extras

| Field            | Type             | Notes                                                                                            |
| ---------------- | ---------------- | ------------------------------------------------------------------------------------------------ |
| `blueprints`     | `BookEntry[]`    | Each entry is a wrapper object, e.g. `{"index": 0, "blueprint": {...}}`. Books may nest books.   |
| `active_index`   | `int`            | Selected slot (0-based).                                                                         |
| `description`    | `string`         |                                                                                                  |

Each `BookEntry`:

```json
{"index": 0, "blueprint": { ... }}
```

The `index` is the slot within the book and must be unique per book. Allowed inner keys: `blueprint`, `blueprint-book`, `deconstruction-planner`, `upgrade-planner`.

### 2.3 `deconstruction-planner` / `upgrade-planner` extras

`deconstruction-planner` settings:

```json
"settings": {
  "entity_filter_mode": 0,         // 0 = whitelist, 1 = blacklist
  "entity_filters": [{"index": 1, "name": "stone-furnace"}],
  "trees_and_rocks_only": false,
  "tile_filter_mode": 0,
  "tile_selection_mode": 0,        // 0 normal, 1 always, 2 never, 3 only
  "tile_filters": [{"index": 1, "name": "landfill"}]
}
```

`upgrade-planner` settings:

```json
"settings": {
  "mappers": [
    {"index": 0, "from": {"type": "entity", "name": "transport-belt"},
                  "to":   {"type": "entity", "name": "fast-transport-belt"}}
  ]
}
```

`type` values: `"entity"` or `"item"`. Quality remapping uses `quality` inside `from`/`to` (see 7).

### 2.4 `Icon`

```json
{"signal": {"type": "item", "name": "iron-plate", "quality": "normal"}, "index": 1}
```

| Field          | Type                                    | Notes                                                                             |
| -------------- | --------------------------------------- | --------------------------------------------------------------------------------- |
| `signal.type`  | `"item" | "fluid" | "virtual" | "entity" | "recipe" | "space-location" | "asteroid-chunk" | "quality"` | Defaults to `"item"` when omitted (legacy export). |
| `signal.name`  | `string`                                | Prototype name.                                                                   |
| `signal.quality` | `string`                              | Optional. See 7.                                                                  |
| `index`        | `int` 1-4                               | Slot in the icon row.                                                             |

---

## 3. Blueprint object schema

Inside `{"blueprint": {...}}`:

| Field                          | Type                       | Notes                                                                                                  |
| ------------------------------ | -------------------------- | ------------------------------------------------------------------------------------------------------ |
| `item`                         | `string` = `"blueprint"`   | Required.                                                                                              |
| `label`                        | `string`                   |                                                                                                        |
| `description`                  | `string`                   |                                                                                                        |
| `icons`                        | `Icon[]`                   | 1-4 entries.                                                                                           |
| `entities`                     | `Entity[]`                 | See section 4. Omitted if empty.                                                                       |
| `tiles`                        | `Tile[]`                   | See section 9. Omitted if empty.                                                                       |
| `wires`                        | `Wire[]`                   | 2.0+. See section 6. Omitted if empty.                                                                 |
| `schedules`                    | `Schedule[]`               | See section 12.                                                                                        |
| `stock_connections`            | `StockConnection[]`        | 2.0 train rolling-stock coupling overrides. Each item is `{stock: int, front?: int, back?: int}` (front/back are `entity_number`s of the connected wagon). [validated 2026-05-09: redruin1/factorio-blueprint-schemas 2.0.0 `stock-connection` definition] |
| `snap-to-grid`                 | `{x:int, y:int}`           | Grid period in tiles. See section 8.                                                                   |
| `absolute-snapping`            | `bool`                     | Defaults to `false` (relative).                                                                        |
| `position-relative-to-grid`    | `{x:int, y:int}`           | Only with absolute snapping.                                                                           |
| `parameters`                   | `Parameter[]`              | 2.0 parametrised blueprints. See section 11.                                                           |
| `version`                      | `int`                      | Packed version (see 2.1).                                                                              |

Field ordering does not matter but the game emits roughly: `icons`, `entities`, `tiles`, `wires`, `schedules`, `parameters`, `item`, `label`, `version`.

---

## 4. Entity schema

Each `Entity` lives in `blueprint.entities`. `entity_number` indexes it from other parts of the blueprint (wires, schedules).

### 4.1 Required fields

| Field           | Type                | Notes                                                                                          |
| --------------- | ------------------- | ---------------------------------------------------------------------------------------------- |
| `entity_number` | `int >= 1`          | Unique within the blueprint. Assigned in placement order; gaps allowed but not idiomatic.      |
| `name`          | `string`            | Prototype name (`"transport-belt"`, `"assembling-machine-2"`, ...).                            |
| `position`      | `{x:number, y:number}` | Tile-center coordinates. See section 10.                                                    |

### 4.2 Common optional fields

| Field                   | Type            | Applies to                          | Notes                                                                                                  |
| ----------------------- | --------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `direction`             | `int`           | Most placeable entities             | 8-way for general, 16-way for rails/elevated rails (section 5). Omitted when `0`.                      |
| `mirror`                | `bool`          | Splitters, refineries, chem plants  | 2.0 entity flip. Omitted when `false`.                                                                 |
| `orientation`           | `float [0,1)`   | Trains, cars, spider-vehicles, artillery turrets | 0 = north, 0.25 = east, 0.5 = south, 0.75 = west.                                       |
| `quality`               | `string`        | Any entity                          | See section 7. Omitted defaults to `"normal"`.                                                         |
| `tags`                  | `dict`          | Any entity                          | Free-form mod data; preserved verbatim.                                                                |
| `items`                 | `ItemRequest[]` | Anything that accepts modules/fuel  | 2.0 list-of-records format (replaced legacy dict). See 4.3.                                            |
| `recipe`                | `string`        | Crafting machines                   | Recipe prototype name.                                                                                 |
| `recipe_quality`        | `string`        | Crafting machines                   | Quality of the produced item (Quality DLC). Defaults to `"normal"`.                                    |
| `bar`                   | `int`           | Containers, cargo wagons            | Slot count after which the inventory is locked.                                                        |
| `inventory`             | `Inventory`     | Cargo wagons                        | `{"filters": Filter[], "bar": int}`.                                                                   |
| `filters`               | `Filter[]`      | Filter inserters, splitters         | `[{"index": int, "name": string, "quality"?: string, "comparator"?: string}]`.                         |
| `filter_mode`           | `string`        | Filter inserters                    | `"whitelist"` or `"blacklist"`.                                                                        |
| `use_filters`           | `bool`          | Splitters, miniloaders              | When `true`, splitter `filters` are honoured.                                                          |
| `request_filters`       | `LogisticSection` | Logistic chests, requesters, spidertrons | 2.0 sectioned format. See 4.4.                                                                |
| `request_from_buffers`  | `bool`          | Requester chest                     |                                                                                                        |
| `override_stack_size`   | `int`           | Inserters                           |                                                                                                        |
| `drop_position`         | `{x,y}`         | Inserters                           | World tile coordinates relative to the entity.                                                         |
| `pickup_position`       | `{x,y}`         | Inserters                           |                                                                                                        |
| `control_behavior`      | `dict`          | Combinators, inserters, belts, lamps, train stops, etc. | See 4.5.                                                                       |
| `connections`           | `dict`          | Pre-2.0 only                        | **Deprecated** in 2.0; replaced by top-level `wires`. Importer should accept and convert if seen.      |
| `neighbours`            | `int[]`         | Pre-2.0 only                        | **Removed** in 2.0 saved blueprints; copper wires now appear in `wires` with `circuit_id` 5 (`pole_copper`). The 2.0 schema has no `neighbours` field on entities. [validated 2026-05-09: redruin1/factorio-blueprint-schemas 2.0.0 entity schema has no `neighbours` key] |
| `station`               | `string`        | Train stops                         | Stop name.                                                                                             |
| `manual_trains_limit`   | `int`           | Train stops                         |                                                                                                        |
| `priority`              | `int`           | Train stops                         | 2.0 stop priority 0-255 (default 50).                                                                  |
| `color`                 | `{r,g,b,a}`     | Trains, train stops, lamps          |                                                                                                        |
| `player_description`    | `string`        | Combinators                         | Per-entity user note.                                                                                  |
| `always_show`           | `bool`          | Combinators                         |                                                                                                        |
| `variation`             | `int`           | `simple-entity-with-owner`, walls   | Sprite variation index.                                                                                |
| `switch_state`          | `bool`          | Power switches                      |                                                                                                        |
| `type`                  | `string`        | Underground belts, loaders, pipes-to-ground | `"input"` or `"output"`.                                                                |
| `parameters`            | `dict`          | Programmable speakers, parametrised entities | Speaker `{playback_volume, playback_globally, ...}`.                                  |

### 4.3 `items` (2.0 module/fuel request format)

```json
"items": [
  {"id": {"name": "speed-module-3", "quality": "rare"},
   "items": {"in_inventory": [
       {"inventory": 4, "stack": 0, "count": 1},
       {"inventory": 4, "stack": 1, "count": 1}
   ]}}
]
```

- `id.name`: item prototype.
- `id.quality`: optional, defaults to `"normal"`.
- `items.in_inventory[*]`: places into a specific inventory index (4 = module slots on assemblers; see Lua `defines.inventory` mirrored in the prototype dump). `stack` is the slot.
- Alternative `items.grid_count` for equipment grids: `{"grid_count": 1}`.

Pre-2.0 form `"items": {"speed-module": 2}` is a legacy importer fallback only.

### 4.4 `request_filters` (logistic sections, 2.0)

```json
"request_filters": {
  "sections": [
    {"index": 1,
     "filters": [
       {"index": 1, "name": "iron-plate", "quality": "normal", "comparator": "=", "count": 200, "max_count": 400}
     ],
     "group": "",
     "multiplier": 1.0,
     "active": true}
  ],
  "trash_not_requested": false,
  "request_from_buffers": true,
  "enabled": true
}
```

Each filter inside a section:

| Field        | Type     | Notes                                                                         |
| ------------ | -------- | ----------------------------------------------------------------------------- |
| `index`      | `int`    | 1-based slot.                                                                 |
| `name`       | `string` | Item or signal name.                                                          |
| `type`       | `string` | `"item"` (default) or `"fluid"`/`"virtual"` for combinator-style filters.     |
| `quality`    | `string` | See 7.                                                                        |
| `comparator` | `string` | One of `"="`, `">"`, `"<"`, `">="`, `"<="`, `"!="`. Default `"="`.            |
| `count`      | `int`    | Requested amount.                                                             |
| `max_count`  | `int`    | Trash threshold (Spidertron, 2.0 logistic groups).                            |

### 4.5 `control_behavior`

A free-form dict whose shape depends on entity type. Common keys:

```json
"control_behavior": {
  "circuit_condition": {"first_signal": {"type":"item","name":"iron-plate"}, "constant": 100, "comparator": ">"},
  "circuit_enable_disable": true,
  "connect_to_logistic_network": false,
  "logistic_condition": {...},
  "circuit_read_hand_contents": false,
  "circuit_hand_read_mode": 0,
  "circuit_set_filters": false,
  "circuit_read_resources": false,
  "circuit_resource_read_mode": 0,
  "use_colors": false,
  "sections": {"sections": [ ... ]}      // constant combinator
}
```

For **arithmetic/decider/selector combinators**, the body is `arithmetic_conditions`, `decider_conditions` (now `conditions: [...]` for the 2.0 multi-condition decider), or `selector_conditions`. For **train stops**, fields like `send_to_train`, `read_from_train`, `read_stopped_train`, `train_stopped_signal`, `set_trains_limit`, `trains_limit_signal`, `read_trains_count`, `trains_count_signal`, `priority_signal`, `set_priority`. For **rail signals**, `red_output_signal`, `orange_output_signal`, `green_output_signal`, `circuit_close_signal`, `circuit_read_signal`. For **lamps**, `use_colors`, `color_mode` (0=signal-color, 1=components, 2=packed-RGB).

---

## 5. Direction enum

> [corrected 2026-05-09: 2.0 unified the direction enum (Friday Facts #378). All
> entities — belts, inserters, assemblers, rails, etc. — serialize using a single
> 16-direction scheme in blueprints. The pre-2.0 8-way enum (E=2) is the OLD
> Lua API value; the blueprint *file* format always uses the 16-way values
> below. East-facing belts are `direction: 4`, not `direction: 2`.]

### 5.1 Unified 16-direction enum (all entities, 2.0+)

```
N=0    NNE=1   NE=2    ENE=3   E=4    ESE=5   SE=6    SSE=7
S=8    SSW=9   SW=10   WSW=11  W=12   WNW=13  NW=14   NNW=15
```

The cardinal-only mapping `{N: 0, E: 4, S: 8, W: 12}` covers belts, undergrounds,
splitters, assemblers, furnaces, mining drills, pumps, gates, walls, chests,
silos, and almost every non-rail entity. The diagonal values `{NE: 2, SE: 6,
SW: 10, NW: 14}` are used by inserters, pumps, and other entities that accept
diagonal placement.

The fine-grained intermediate values (1, 3, 5, 7, 9, 11, 13, 15) are only used
by 2.0 rail prototypes:

- `straight-rail`, `half-diagonal-rail`, `curved-rail-a`, `curved-rail-b`
- Space Age elevated rails: `elevated-straight-rail`, `elevated-half-diagonal-rail`, `elevated-curved-rail-a`, `elevated-curved-rail-b`
- `rail-ramp`, `rail-support`
- Rolling stock orientation snap (the entity uses `orientation` as canonical, but `direction` is also serialised in 16-way for placement ghosts).

Saved blueprints elide `direction` when it equals `0`.

### 5.2 Mapping from the old 8-way enum

If you have legacy code or pre-2.0 blueprint data, double the value to convert:
old `direction × 2` = new `direction`. Example: an east-facing belt was `2` in
1.x, is `4` in 2.0+.

---

## 6. Wires (2.0)

Top-level `blueprint.wires` is an array of 4-tuples:

```json
[entity_id, source_circuit_id, target_entity_id, target_circuit_id]
```

All four are integers. The pre-2.0 per-entity `connections` dict is gone in saved blueprints; importers should still accept it for back-compat.

Each tuple is undirected (the wire is the same regardless of which side is "source"); the game emits each wire exactly once.

### 6.1 `circuit_id` values

These map directly to `defines.wire_connector_id` in the Lua API.

| Value | `wire_connector_id`           | Meaning                                                |
| ----- | ----------------------------- | ------------------------------------------------------ |
| 1     | `circuit_red` / `combinator_input_red`   | Red wire, default circuit / combinator input |
| 2     | `circuit_green` / `combinator_input_green` | Green wire, default circuit / combinator input |
| 3     | `combinator_output_red`       | Red wire, combinator output                            |
| 4     | `combinator_output_green`     | Green wire, combinator output                          |
| 5     | `pole_copper` / `power_switch_left_copper` | Copper wire on power pole / power-switch left terminal |
| 6     | `power_switch_right_copper`   | Copper wire on power-switch right terminal             |

> [validated 2026-05-09: redruin1/factorio-blueprint-schemas `schemas/2.0.0/blueprint.json` `wire-connector-id` enum] Power-switch right terminal is `6`; left terminal shares `5` with the regular pole connector.

### 6.2 Examples

```json
"wires": [
  [1, 1, 2, 1],   // red wire between entity 1 and entity 2 (both default-circuit)
  [3, 2, 4, 4],   // green wire from entity 3 (input) to entity 4 (output, decider)
  [5, 5, 6, 5]    // copper wire between two power poles
]
```

---

## 7. Quality field

Quality DLC adds a string tag on entities, items, recipes, and signals:

```
"normal"    (level 0, omitted when default)
"uncommon"  (level 2)
"rare"      (level 4)
"epic"      (level 6)
"legendary" (level 10)
```

Mods can add more (level granularity matters for prototype lookups). Locations:

- Entity: `entity.quality`.
- Item request: `items[*].id.quality`.
- Recipe: entity `recipe_quality` (and `recipe` itself stays a name string).
- Signal: `signal.quality`.
- Logistic filter: `filters[*].quality` plus `comparator` to express "rare or better" via `">="`.

Example (legendary speed-3 modules in a rare assembler making rare iron gears):

```json
{"entity_number": 1, "name": "assembling-machine-3", "position": {"x": 0.5, "y": 0.5},
 "quality": "rare", "recipe": "iron-gear-wheel", "recipe_quality": "rare",
 "items": [{"id": {"name": "speed-module-3", "quality": "legendary"},
            "items": {"in_inventory": [
              {"inventory": 4, "stack": 0, "count": 1},
              {"inventory": 4, "stack": 1, "count": 1},
              {"inventory": 4, "stack": 2, "count": 1},
              {"inventory": 4, "stack": 3, "count": 1}
            ]}}]}
```

---

## 8. Snap-to-grid

```json
"snap-to-grid": {"x": 4, "y": 4},
"absolute-snapping": true,
"position-relative-to-grid": {"x": 0, "y": 0}
```

Semantics:
- `snap-to-grid`: when set, the blueprint's bounding box snaps to an `x` by `y` tile grid as it is placed.
- `absolute-snapping`: `false` (default) snaps relative to the cursor; `true` snaps to world coordinates.
- `position-relative-to-grid`: only meaningful with absolute snapping, offsets the blueprint within each grid cell.

Diagram (4x4 absolute snap, offset (0,0)):

```
World tiles . . . . | . . . . | . . . .
              cell 0,0          cell 1,0
                +-----+
                | BP  |
                +-----+
```

Toggling `absolute-snapping` true with `position-relative-to-grid (1,1)` shifts every cell by (1,1).

---

## 9. Tile schema

```json
{"name": "stone-path", "position": {"x": 0, "y": 0}}
```

Fields:

| Field      | Type     | Required | Notes                                                                |
| ---------- | -------- | -------- | -------------------------------------------------------------------- |
| `name`     | `string` | yes      | Tile prototype name.                                                 |
| `position` | `{x,y}`  | yes      | **Top-left corner** of the tile (integer coordinates). NOT centered. |

Common placeable tile names (verified against `data.raw.tile`): `stone-path`, `concrete`, `refined-concrete`, `hazard-concrete-left`, `hazard-concrete-right`, `refined-hazard-concrete-left`, `refined-hazard-concrete-right`, `landfill`, `artificial-yumako-soil`, `artificial-jellynut-soil`, `overgrowth-yumako-soil`, `overgrowth-jellynut-soil`, `ice-platform`, `foundation`, `space-platform-foundation`. All serialise identically; only the `name` changes.

Position semantics for tiles vs entities is the most-common gotcha. See section 10.

---

## 10. Position math

### 10.1 Coordinate system

- `+x` is east, `+y` is south. Origin (0,0) is at one tile corner.
- **Entity positions** are the **center** of the entity's collision/selection box.
- **Tile positions** are the **top-left corner** of the tile.

### 10.2 Entity center rules (verified against `selection_box` in the prototype dump)

| Entity tile size                   | Center coordinates                                | Examples                                                       |
| ---------------------------------- | ------------------------------------------------- | -------------------------------------------------------------- |
| 1x1                                | integer `(x, y)`                                  | belt, inserter, small pole, lamp, signal                       |
| 2x2                                | half-integer `(x.5, y.5)`                         | assembler-2/3, chest, medium pole, chemical plant (3x3 actually -> int) |
| 3x3                                | integer `(x, y)`                                  | assembling-machine-1/2/3 (3x3 footprint), chemical plant       |
| 2x1 or 1x2                         | one axis half, other integer                      | splitter (2 tiles wide x 1 deep -> `(x, y.5)` when N/S)        |
| 4x4 (boiler? big pole)             | half-integer `(x.5, y.5)`                         | substation (2x2 -> half), nuclear reactor (5x5 -> int)         |
| 5x5, 3x3, odd squares              | integer                                           | nuclear reactor, refinery (5x5)                                |

General rule: center axis is half-integer if and only if the tile span on that axis is even. Splitters are 2 wide x 1 deep, so when facing N/S they sit at `(int+1, int+0.5)`; rotated 90 degrees they sit at `(int+0.5, int+1)`.

### 10.3 Verified examples (from `data-raw-dump.json`)

| Entity                | `selection_box` (from dump)         | Tile span | Center if NW corner is (0,0) |
| --------------------- | ----------------------------------- | --------- | ---------------------------- |
| `transport-belt`      | `[[-0.5,-0.5],[0.5,0.5]]`           | 1x1       | `(0, 0)`                     |
| `splitter`            | `[[-0.9,-0.5],[0.9,0.5]]`           | 2x1       | `(0.5, 0)` facing E/W; `(0, 0.5)` facing N/S |
| `assembling-machine-2`| `[[-1.5,-1.5],[1.5,1.5]]`           | 3x3       | `(0, 0)`                     |
| `straight-rail`       | `[[-1.7,-0.8],[1.7,0.8]]` (2x2 grid)| 2x2       | `(0.5, 0.5)`                 |

### 10.4 Tiles

Tiles use the top-left corner. A 1x1 tile that visually covers the same spot as a 1x1 entity at `(0, 0)` is at `(0, 0)`. A 2x2 entity at `(0.5, 0.5)` covers tiles `(0, 0)` through `(1, 1)`.

---

## 11. Parametrised blueprints (2.0)

A blueprint may declare numeric/signal parameters that are substituted at paste time. Lives at `blueprint.parameters`.

```json
"parameters": [
  {"type": "id",      "name": "p1", "id": "iron-plate", "quality-condition": {"quality": "normal", "comparator": "="}, "ingredient-of": "p2"},
  {"type": "number",  "name": "p2", "number": "100",    "variable": "x",       "formula": "x * 2"}
]
```

| Field                 | Type      | Notes                                                                          |
| --------------------- | --------- | ------------------------------------------------------------------------------ |
| `type`                | `string`  | `"id"` (signal/item/recipe slot) or `"number"` (numeric value).                |
| `name`                | `string`  | Parameter handle. Referenced from labels, icons, and entity fields as `parameter-N` where N matches the array index (0-based) or via `name`. |
| `id`                  | `string`  | Default item/signal name, for `type: "id"`.                                    |
| `quality-condition`   | object    | Optional default quality and comparator for the id.                            |
| `ingredient-of` / `product-of` | `string` | Cross-reference to another id parameter, used to derive ingredients/products. |
| `number`              | `string`  | Default numeric value for `type: "number"` (string to allow large ints).       |
| `variable`            | `string`  | Variable name exposed in `formula` of *other* parameters.                      |
| `formula`             | `string`  | Expression evaluated on paste; supports `+ - * / % ^`, `min`, `max`, parentheses, and other parameters by their `variable`. |

### 11.1 Substitution syntax

Inside `label`, `description`, icon `signal.name`, and entity `name`/`recipe`/`items[].id.name`, the literal token `parameter-N` (zero-based index into `parameters`) is replaced. Example label: `"Smelter for [item=parameter-0]"` would render with whatever id parameter 0 resolves to.

Number parameters expose helpers in `formula` strings: `pN_s` evaluates to "stack size of parameter N" (so `p0_s` is the chosen item's stack size). The literal `parameter-N` is a synthetic prototype name — codecs must preserve it as-is and not validate it against the prototype dump.

> [validated 2026-05-09: FFF-392 (factorio.com/blog/post/fff-392) and redruin1/factorio-blueprint-schemas 2.0.0 `id-parameter`/`number-parameter` definitions] The synthetic name format `parameter-N` is the canonical replacement token; the engine rewrites these in place at paste time after the user fills in the parameter dialog.

---

## 12. Schedules (trains)

```json
"schedules": [
  {"locomotives": [3, 7],
   "schedule": {
     "records": [
       {"station": "Iron Pickup",
        "wait_conditions": [
          {"type": "item_count",
           "compare_type": "or",
           "condition": {"first_signal": {"type": "item", "name": "iron-ore"},
                         "constant": 4000,
                         "comparator": ">="}},
          {"type": "inactivity", "compare_type": "and", "ticks": 300}
        ]},
       {"station": "Iron Drop",
        "wait_conditions": [{"type": "empty", "compare_type": "or"}]}
     ],
     "group": "",
     "interrupts": []
   }}
]
```

| Field                             | Type     | Notes                                                                                            |
| --------------------------------- | -------- | ------------------------------------------------------------------------------------------------ |
| `locomotives`                     | `int[]`  | `entity_number`s of locomotives sharing this schedule.                                           |
| `schedule.records[].station`      | `string` | Stop name. Mutually exclusive with `rail`/`temporary`.                                           |
| `schedule.records[].rail`         | `int`    | Rail entity for temporary stops.                                                                 |
| `schedule.records[].temporary`    | `bool`   |                                                                                                  |
| `wait_conditions[].type`          | `string` | See list below. |
| `wait_conditions[].compare_type`  | `string` | `"and"` or `"or"`.                                                                               |
| `wait_conditions[].ticks`         | `int`    | For `time` and `inactivity`.                                                                     |
| `wait_conditions[].condition`     | object   | Standard `{first_signal, second_signal/constant, comparator}`.                                   |
| `schedule.group`                  | `string` | 2.0 train group name (empty = no group).                                                         |
| `schedule.interrupts[]`           | array    | 2.0 interrupt records: `{name, conditions, targets, inside_interrupt}`.                          |

#### 12.1 `wait_conditions[].type` enumeration (2.0)

[validated 2026-05-09: redruin1/factorio-blueprint-schemas 2.0.0 `train-wait-condition` / `train-interrupt-condition` unions]

**Train wait conditions (used in `records[].wait_conditions`):**
`circuit`, `empty`, `fluid_count`, `fuel_item_count_all`, `fuel_item_count_any`, `full`, `fuel_full`, `not_empty` (renamed from "Has Cargo"), `inactivity`, `item_count`, `passenger_not_present`, `passenger_present`, `specific_destination_full`, `specific_destination_not_full`, `time`.

**Interrupt-only conditions (used in `interrupts[].conditions`, in addition to all wait conditions except `inactivity` and `time`):**
`at_station`, `destination_full_or_no_path`, `not_at_station`, `all_requests_satisfied`, `any_request_not_satisfied`, `any_request_zero`, `damage_taken`, `request_satisfied`, `request_not_satisfied`, `any_planet_import_zero`.

> [corrected 2026-05-09: previously listed `robots_inactive`, which is not in the 2.0 schema; added `fuel_item_count_all`/`_any`, `fuel_full`, `not_empty`, `specific_destination_full/_not_full`, `any_planet_import_zero`.]

---

## 13. Space platform blueprints

Space platform blueprints share the wrapper format. Differences:

- The blueprint typically contains a `space-platform-hub` entity and `space-platform-foundation` tiles.
- Hub `position` is at the platform origin (3x3 footprint -> integer center).
- `cargo-bay` and `cargo-landing-pad` may appear; they have specific orientation rules.
- `asteroid-collector` carries an `orientation` (float 0-1) plus a `direction` for arm rotation; both are emitted.
- `thruster` entities have an attached `direction`.
- Tiles outside `space-platform-foundation` / `space-platform-foundation-2` / `decorative-foundation` will fail to apply on a platform; only foundation-family tiles are valid in space-platform blueprints.
- The wrapper field `item` is still `"blueprint"` - there is no separate `space-platform-blueprint` item kind in 2.0.76. The game inspects the entities/tiles to decide if the blueprint is platform-only.

---

## 14. Required-vs-optional matrix (cheat sheet)

| Object              | Always present                                         | Always optional                              |
| ------------------- | ------------------------------------------------------ | -------------------------------------------- |
| Wrapper             | `item`, `version`                                      | `label`, `description`, `icons`, `label_color` |
| Blueprint           | `item`, `version`                                      | everything else (empty arrays elided)        |
| Entity              | `entity_number`, `name`, `position`                    | all other fields                             |
| Tile                | `name`, `position`                                     | none                                         |
| Wire tuple          | all four ints                                          | none                                         |
| Icon                | `signal.name`, `index`                                 | `signal.type`, `signal.quality`              |
| Schedule record     | (`station` xor `rail`)                                 | `wait_conditions`, `temporary`               |
| Wait condition      | `type`, `compare_type`                                 | `condition`, `ticks`                         |

---

## 15. Validation

A JSON Schema covering the above is at `specs/blueprint_schema.json` (draft 2020-12). Run:

```
python3 -c "import json,jsonschema; jsonschema.validate(json.load(open('bp.json')), json.load(open('specs/blueprint_schema.json')))"
```

Codec: `tools/blueprint_codec.py`. CLI:

```
python3 tools/blueprint_codec.py decode '0eNp...'
python3 tools/blueprint_codec.py encode bp.json
```
