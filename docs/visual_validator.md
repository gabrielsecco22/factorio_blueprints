# Visual blueprint validator

Two pieces working together:

1. **`tools/render_blueprint.py`** -- pure-Python (stdlib only) decoder
   plus ASCII renderer plus structural summary. Reuses
   `tools/blueprint_codec.py` for decoding and
   `harness/catalog.py::footprint(name)` for entity sizes. Crosses
   `specs/items.json` against `~/.factorio/mods/mod-list.json` to flag
   entities from disabled or missing mods. Hard-capped at 1000x1000
   tiles per render.
2. **`.claude/agents/blueprint-visual-validator.md`** -- a project-scoped
   sub-agent definition. Given a blueprint string and the original
   `BuildSpec`, it decodes + renders + computes throughput +
   cross-checks entity-spec match, belt tier, fuel feed, power
   coverage, and mod compatibility, then emits a structured Markdown
   verdict (`PASS|FAIL|WARN`) with concrete coordinates and suggested
   fixes for the generator agent. Read-only: never mutates blueprints.

## CLI usage

```sh
# Full output (ASCII grid + JSON summary).
python3 tools/render_blueprint.py "$BP_STRING"

# Or pass a file containing the blueprint.
python3 tools/render_blueprint.py path/to/blueprint.txt

# Just the structural JSON.
python3 tools/render_blueprint.py --json "$BP_STRING"

# Just the ASCII grid.
python3 tools/render_blueprint.py --grid-only "$BP_STRING"

# Window into a huge blueprint.
python3 tools/render_blueprint.py --bbox 0,0,80,40 "$BP_STRING"

# Truncate excessively wide rows in the printed grid.
python3 tools/render_blueprint.py --max-width 200 "$BP_STRING"
```

## Symbol table

See the agent definition (`.claude/agents/blueprint-visual-validator.md`)
and the docstring at the top of `tools/render_blueprint.py` for the full
symbol table. Highlights:

- Crafting machines: `F` furnace, `A` assembler, `E` EM-plant,
  `Y` foundry / centrifuge, `K` chemical-plant / crusher, `O` refinery,
  `R` recycler, `B` boiler / burner-mining-drill,
  `M` electric-mining-drill, `L` lab, `H` beacon.
- Logistics: `>` `<` `^` `v` belts (uppercase = underground-belt),
  `i` `u` `{` `}` inserters facing N/S/E/W (uppercase = fast / bulk /
  stack / filter / long-handed -- check `entity_counts` to resolve).
- Power: `+` electric pole, `#` substation, `S` solar-panel,
  `Q` accumulator, `N` reactor / heat-exchanger / heat-pipe.
- Storage / fluid: `C` chest, `=` pipe / tank, `|` pipe-to-ground.
- `'` continuation tile of a multi-tile entity.
- `.` empty.
- `?` unknown entity OR non-cardinal direction (renderer also emits a
  per-entity warning).

## Tests

```sh
python3 -m unittest validation.test_render
```

Covers the stone smelter array (counts of `F`, `i`, `>`), the solar
field (counts of `S`, `Q`, `+`, by-category aggregation), mod-name
resolution for both known-mod and unknown entities, and the `--bbox` /
`--max-width` clipping flags.

## Known limitations

- Belt continuity, inserter-reach geometry, and substation-coverage
  geometry are not yet computed by the renderer; the validator agent
  performs those checks itself from the JSON summary plus the raw
  decoded entities. A follow-up could move the geometry into
  `render_blueprint.py` so non-agent callers benefit.
- Blueprint books (`{"blueprint_book": ...}`) are not supported;
  callers must extract a single blueprint first. The renderer raises a
  clear error.
- Non-cardinal directions (NE/SE/SW/NW for ramps and rails) render as
  `?` and trigger a per-entity warning. Rails and trains aren't part
  of the current generator output, so this is fine for now.
- Tile entries (`tiles`) are counted but not drawn; the grid only
  shows entities. Stone paths, refined concrete etc. live in
  `summary.tiles`.
