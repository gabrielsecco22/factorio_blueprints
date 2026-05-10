# Extending FBE for new mods

The vendored Factorio Blueprint Editor (FBE) bundle under
`studio/static/fbe/` ships only `__base__` + `__core__` prototypes.
`tools/extend_fbe_for_mods.py` patches the bundle's `data.json` with
DLC + mod prototypes from `specs/data-raw-dump.json` and copies the
matching PNG sprites out of the local Factorio install.

This file documents how the extension works and what to do when a new
mod adds an entity that isn't rendering.

## How it works

### Inputs

- `specs/data-raw-dump.json` -- live `factorio --dump-data` output.
  The single source of truth for prototype values. Always reflects the
  user's exact enabled mod set.
- `~/.factorio/mods/mod-list.json` -- which mods to look in for sprites.
- `~/.local/share/Steam/steamapps/common/Factorio/data/<source>/` --
  base game + DLC sprites (`base`, `space-age`, `quality`,
  `elevated-rails`, `core`).
- `~/.factorio/mods/<ModName>_<version>.zip` -- modded sprites.

### Pipeline

1. **Diff `data.json` vs the dump.** Find every entity / item / recipe
   / fluid in the dump that's missing from FBE.
2. **Add missing entries.** Copy each missing entry verbatim from the
   dump into `data.json`. The dump uses the same JSON shape FBE
   expects, so no transformation is needed -- we even keep the same
   `__source__/path.png` filename schema.
3. **Overlay modded parameters.** For entities that already exist in
   FBE but have different values in the dump (typical example:
   AdjustableModule increases `beacon.module_slots` from 2 to 5),
   overlay a small whitelist of fields:

       module_slots, allowed_effects, allowed_module_categories,
       effect_receiver, energy_usage, energy_source, crafting_speed,
       crafting_categories, max_health, supply_area_distance,
       distribution_effectivity, distribution_effectivity_bonus_per_quality_level,
       profile, researching_speed, science_pack_drain_rate_percent,
       neighbour_bonus, max_energy_production, fluid_usage_per_tick,
       maximum_temperature, result_inventory_size, source_inventory_size,
       input_fluid_box, output_fluid_box, fluid_boxes,
       rocket_parts_required, fast_replaceable_group

   The whitelist is in `OVERLAY_FIELDS_ENTITY` in
   `tools/extend_fbe_for_mods.py`. Sprite/circuit-connector geometry
   is left untouched.
4. **Collect PNG references.** Walk every newly-added or overlaid
   entry and regex out every `__source__/path.png` string.
5. **Resolve and copy sprites.** For each reference:
   - `__base__`, `__core__`, `__space-age__`, `__quality__`,
     `__elevated-rails__`: look in the game install at
     `<install>/data/<source>/<rel>` and copy the file as-is.
   - `__<ModName>__`: open the matching zip at
     `~/.factorio/mods/<ModName>_*.zip` and extract
     `<ModName>_<version>/<rel>` (or whatever the inner top-level
     directory is -- we probe the zip).
   - Destination: `studio/static/fbe/data/__<source>__/<rel>`.
6. **Patch the FBE bundle.** The upstream PixiJS loader does
   `${path.replace(".png",".basis")}` because the cloud build
   pre-converts PNGs to Basis Universal. We don't have `basisu`, so
   we replace the substring with `${path.replace(".png",".png"  )}`
   (same byte length, no-op) and let PixiJS load PNG directly. PixiJS
   already supports PNG natively (you can see `.jpg`, `.png`, `.webp`,
   `.avif` in its loader-extension list).

### Idempotency

The extension writes a `__factudio_extension__` sentinel at the top of
the patched `data.json`. Re-running detects it and only adds new
prototypes. Pass `--force` to first restore from
`data.json.upstream` (created on the first successful run) and then
re-extend.

The bundle JS patch is also idempotent: we look for the original
`.replace(".png",".basis")` substring, so once patched, subsequent
runs skip the file.

## Adding a new mod that ships entities

The script auto-discovers every enabled mod from `mod-list.json`. If a
new mod adds an entity, there are usually no code changes needed:

1. Make sure the mod is enabled in `~/.factorio/mods/mod-list.json`.
2. Re-dump prototypes: `bash tools/dump_prototypes.sh`.
3. Re-run the extension: `python3 tools/extend_fbe_for_mods.py --force`.

The new entity will be added to `data.json` and its sprites copied
from the mod zip.

### Things to check if it doesn't work

**The entity's `type` isn't in `RENDERABLE_TYPES`.** The list at the
top of `tools/extend_fbe_for_mods.py` enumerates the entity types
FBE's renderer knows how to draw (we grep them out of the bundled
JS). If the new entity introduces a brand-new top-level type
(e.g. some hypothetical `super-foundry` type with no analog in the
base game), FBE will treat it as an unknown placeholder. Workaround:
either (a) add the type to `RENDERABLE_TYPES` and accept the
placeholder render, or (b) rewrite the prototype's `type` to the
nearest base equivalent (`assembling-machine` for any crafter with
recipes, `furnace` for fixed-recipe smelters).

**The mod ships sprites under a non-standard path.** The script uses
the literal `__source__/path.png` strings in the dump. Most mods get
this right because Factorio enforces the convention. If a mod ships
sprites that the script can't find, the missing files will be listed
under "Missing sprites" in the script's summary. Common causes:

- Mod name uses spaces or capitalisation that doesn't match the zip
  name. Rename the zip or add an entry to `_SOURCE_ALIASES`.
- Mod ships sprites under `__core__/` (cross-mod borrow). The
  extension already handles this because `__core__` is always a
  resolved source.
- Sprite is a generated atlas (some big mods build sheet textures at
  runtime in Lua). These don't appear on disk; placeholder render is
  unavoidable.

**The dump is stale.** Re-run `bash tools/dump_prototypes.sh` to
refresh. Mod updates and mod settings changes both invalidate the
dump.

## What about `basisu`?

The original FBE cloud bundle uses Basis Universal-compressed sprite
atlases for compactness (~10-20% the size of PNG). We don't use
`basisu` because:

- It's not in any common Linux package repo (would need a manual
  build from source via `cmake basis_universal`).
- Our local install path is bandwidth-free anyway -- the sprites are
  on the same machine.
- PNG decode is faster on the GPU side once Basis transcoding is
  removed from the critical path.

If you ever need to drop in `basisu` (e.g. to rebuild the bundle for
upload to a real CDN), the conversion is roughly:

    basisu -file foo.png -ktx2 -comp_level 4 -output foo.basis

and you'd undo the JS patch (`.replace(".png", ".basis")`) so the
loader looks for the `.basis` siblings again.

## Disk footprint

For the calibration target (Factorio 2.0 + Space Age + Quality +
Elevated Rails + ~30 mods), the extension copies ~1300 PNGs totalling
~315 MB into `studio/static/fbe/data/__*__/`. All of that lives under
the gitignored `studio/static/fbe/` tree.

To reset: delete `studio/static/fbe/data/__<source>__/` (any subdir
other than `__base__` / `__core__`) and re-run with `--force`. To
fully reset the bundle, delete `studio/static/fbe/` and re-run
`bash studio/setup_fbe.sh`.
