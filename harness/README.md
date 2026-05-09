# `harness/`

Deterministic Python pipeline that turns a `BuildSpec` into a paste-ready
Factorio 2.0.76 blueprint string. Each stage is a separate module so a
future LLM-driven version can swap any stage for a sub-agent without
re-architecting the pipeline.

## Pipeline

```
BuildSpec
   |
   |   spec.py
   v
ProductionPlan        <- plan.py     (recipe + machine + count)
   |
   v
LayoutResult          <- layout.py   (entity positions, directions)
   |
   v
blueprint dict        <- orchestrator.py
   |
   v
ValidationReport      <- validate.py (collisions, belts, inserters,
   |                                  power, JSON Schema)
   v
blueprint string      <- encode.py   (zlib + base64 + version byte)
```

The orchestrator runs all stages and returns a `SynthesisResult` with the
blueprint string, the decoded blueprint dict, the entity count, any
warnings, and a markdown summary.

## Quick start

```python
from harness import BuildSpec, synthesize

spec = BuildSpec(
    kind="smelter_array",
    target="iron-plate",
    machine_count=12,
    machine_choice="stone-furnace",
    fuel="coal",
    inserter_tier="burner-inserter",
)
result = synthesize(spec)
print(result.blueprint_string)
print(result.report)
```

Or run an example end-to-end:

```sh
python3 -m harness.examples.stone_smelter_array
python3 -m harness.examples.solar_field
python3 -m harness.examples.beacon_smelter_array
```

Available example builds:

| Example                      | Kind                        | What it produces |
| ---------------------------- | --------------------------- | ---------------- |
| `stone_smelter_array`        | `smelter_array`             | 12 stone furnaces, no fuel feed (MVP) |
| `steel_smelter_array`        | `smelter_array`             | 24 steel furnaces with shared coal/ore belt |
| `electric_smelter_array`     | `electric_smelter_array`    | 24 electric furnaces with substation power |
| `solar_field`                | `solar_field`               | 24 panels + 20 accumulators, medium poles |
| `green_circuit_block`        | `green_circuit_block`       | 4 cable + 6 circuit assemblers, two-row layout |
| `beacon_smelter_array`       | `beacon_smelter_array`      | 12 electric furnaces with 24 vanilla beacons (speed-3) and productivity-3 modules |

## Tests

```sh
python3 -m unittest harness.tests.test_examples
```

Each test asserts:

- the blueprint string round-trips through the codec,
- `validate.py` reports no errors (collisions, belt continuity,
  inserter reach, power coverage),
- the decoded JSON validates against `specs/blueprint_schema.json`
  (skipped with a warning if `jsonschema` is not importable),
- the entity counts match the documented example.

## Adding a new example

1. Decide whether your build is throughput-driven (smelter, assembler,
   chemical plant), fixed-shape (solar field, beacon array), or both.
2. Add a `kind` value to `spec.BuildSpec` if your build doesn't fit an
   existing kind.
3. Wire the new kind into `plan.plan()` and `layout.layout()`. Reuse
   helpers from `catalog.py` (footprints, item lookups, recipe categories).
4. Place entities through `LayoutResult.place(name, nw_tile, direction=...)`.
   The result tracks tile occupancy for collision-free placement.
5. Drop a runnable example in `harness/examples/<name>.py`. It should:
   - import `BuildSpec` and `synthesize`,
   - return a `SynthesisResult`,
   - print the blueprint string when run as `python3 -m harness.examples.<name>`.
6. Add a test in `harness/tests/test_examples.py` that:
   - asserts the round-trip,
   - asserts the entity breakdown,
   - asserts validation passes.

## Module reference

| File | Responsibility |
| ---- | -------------- |
| `spec.py`         | `BuildSpec` dataclass; the only input the pipeline needs. |
| `catalog.py`      | Lazy loaders for `specs/*.json` plus a footprint table. |
| `plan.py`         | `BuildSpec` -> `ProductionPlan` (recipe, machine, count, throughput). |
| `layout.py`       | `ProductionPlan` -> `LayoutResult` (placed entities, direction enum, collision-checked grid). |
| `wiring.py`       | Stub for v2; belt + inserter wiring is currently inline in `layout.py`. |
| `power.py`        | Stub for v2; pole placement is currently inline in `layout.py`. |
| `validate.py`     | Collision, belt continuity, inserter reach, power coverage, JSON Schema. |
| `encode.py`       | Wraps `tools/blueprint_codec.py`. Owns the packed-version constant for 2.0.76. |
| `orchestrator.py` | Runs the pipeline, builds the blueprint dict, calls validate, encodes. |
| `examples/`       | Runnable, importable example builds. |
| `tests/`          | unittest test cases for each example. |

## Coordinate convention

- `+x` east, `+y` south. Matches `docs/blueprint_format.md`.
- Internally we work in **tile coordinates**, anchored so the NW corner
  of the bounding box is at (0, 0).
- Blueprint `position` is computed as `NW_tile + (tile_size - 1) / 2`,
  giving:
  - `1x1` -> integer (e.g. `(0, 0)` for tile NW=(0,0))
  - `2x2` -> half-integer (e.g. `(0.5, 0.5)`)
  - `3x3` -> integer (e.g. `(1, 1)`)
- `direction` uses the 16-way enum (Factorio 2.0 unification, FFF-378):
  N=0, E=4, S=8, W=12. Cardinal only in the MVP.

## Known limitations

See `KNOWN_LIMITATIONS.md`.
