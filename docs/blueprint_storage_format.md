# `blueprint-storage-2.dat` binary format

Notes on the on-disk format of Factorio 2.0's personal blueprint
library file. Calibrated against the user's
`/home/gabriel/.factorio/blueprint-storage-2.dat` (Factorio 2.0.76,
Space Age + Quality + Elevated Rails, 38 mods enabled).

The format is undocumented by Wube. Everything below was reverse-
engineered from the file itself plus the asheiduk Factorio Blueprint
Decoder for 1.x ([asheiduk/factorio-blueprint-decoder]
(https://github.com/asheiduk/factorio-blueprint-decoder)). The 2.0
format diverges from 1.x in several places, noted inline.

The implementation lives in `tools/blueprint_storage_format.py`. The
table below describes what is verified ("V"), partially verified ("P"),
or unknown ("?").

## File-level layout

```
header               -- V
library_state        -- V
object[ object_count ] -- P (envelope V; body P or ?)
```

All multi-byte integers are little-endian. Strings use a length-prefix
encoded by `count()`: a single `u8`; if that byte is `0xFF` then a
`u32` follows. (1.x used the same scheme.)

### Header

| Offset (sample) | Size | Field | Notes | State |
|----------------:|-----:|-------|-------|-------|
| `0x000` | 8 | `version` | 4 x `u16` LE: major, minor, patch, developer. Sample: `02 00 00 00 4c 00 00 00` -> 2.0.76.0 | V |
| `0x008` | 1 | sentinel | always `0x00` | V |
| `0x009` | 1 | `migration_count` | `count8` (no 0xFF escape observed for this field) | V |
| `0x00a` | varies | `migrations[]` | each entry is `(string mod_name, string source_file)` | V |
| -- | 2 | `prototype_category_count` | `count16` (LE u16) | V |
| -- | varies | `prototype_categories[]` | see below | V |
| -- | 1 | `lib_state` | observed `0x00` | V |
| -- | 1 | sentinel | observed `0x00` | V |
| -- | 4 | `generation_counter` | `u32`. Increments each save. Sample: 1048 | V |
| -- | 4 | `unix_timestamp` | `u32` seconds. Sample: 1778302043 -> 2026-05-09 01:47:23 UTC-3 | V |
| -- | 4 | reserved | observed all zeros | V |
| -- | 1 | sentinel | observed `0x01` | V |
| -- | 4 | `object_count` | `u32`. Sample: 79 | V |

`object_count` counts top-level slots, not just used ones. Slots can
be marked unused (see "Object envelope" below).

### Prototype index entry

Each category looks like:

```
string  category_name
count   name_count        # see width rule below
name[name_count]
    u8/u16  prototype_id  # width matches the count width
    string  internal_name
```

**Width rule (2.0):** the `quality` category uses `count8 + u8` ids;
every other category uses `count16 + u16`. (This is inverted from 1.x,
where `tile` was the special-case category.)

The category names observed in the user's file: `accumulator`,
`agricultural-tower`, `ammo-turret`, ..., `quality`, `planet`,
`space-location`. Total: 102 categories, 776 prototype names.

The four library-object categories (`blueprint`, `blueprint-book`,
`deconstruction-item`, `upgrade-item`) live in this same index. Their
prototype IDs are referenced by `item_id` in each object envelope.

## Object envelope

Each top-level object starts with one byte. If `0x00` the slot is
unused (no further payload); otherwise it must be `0x01`.

```
u8     is_used                 # 0x00 = empty slot, 0x01 = present
u8     prefix_byte             # 0=blueprint 1=book 2=decon 3=upgrade
u32    generation
u16    item_id                 # references prototype_index
string label
string description
... handler-specific bytes
```

Verified prefix bytes:

| Prefix | Object kind |
|-------:|-------------|
| 0 | blueprint |
| 1 | blueprint-book |
| 2 | deconstruction-planner *(observed in nested data; not on top-level slots in this file)* |
| 3 | upgrade-planner *(same)* |

### Blueprint body (prefix = 0) -- V

```
u8     reserved   # observed 0x00
count  content_size
bytes  content[content_size]
```

`content_size` uses the standard `count()` encoding: usually escaped
to a `u32` (the marker byte `0xFF`) because the body is large.

The `content` body itself is the inner blueprint -- it begins with its
own version stamp, migrations table, prototype index, and then the
"true" blueprint payload (label, icons, snap-to-grid, entities, tiles,
schedules, ...). We do **not** parse the inner body here. The
`tools/blueprint_codec.py` module decodes the *blueprint string* form
(deflate + base64 + JSON), which is what the in-game "Export string"
button produces and what `import-string` consumes.

### Blueprint-book body (prefix = 1) -- ?

After `description`, the book has additional bytes that we have not
yet decoded. The first nested object header looks plausible at
roughly +6 bytes from the end of the description, but the full
sequence (icons list? active slot? nested object count?) is not
nailed down.

Top-level walking therefore stops at the first book.

### Deconstruction & upgrade planners (prefix = 2/3) -- ?

Not analysed. The asheiduk 1.x decoder shows fields for filter
entries, tile selection mode, and tree/rock filters; the 2.0
equivalents are likely similar but unverified.

## What we read vs what we skip

`tools/blueprint_storage_format.py::parse_storage` returns a list of
`LibraryEntry` and stops at the first unsupported object. Result on
the calibration file (`gabriel`'s 36 MB library):

```
factorio version: 2.0.76.0
migrations: 18
prototype categories: 102
object_count (header): 79
entries walked: 5 (used=5, drifted=1)
```

The walk terminates at the first blueprint-book ("Fleet") because we
cannot reliably skip past book contents without a full parser.

## Manual export workflow (recommended for now)

Until binary decoding is reliable end-to-end, treat
`blueprint-storage-2.dat` as opaque and use the in-game UI:

1. Open the blueprint library in-game (`B`).
2. Right-click a blueprint or book and choose **Export string**.
3. Copy the resulting string and feed it to the local mirror:

   ```sh
   python3 tools/blueprint_storage.py import-string '<paste>' my-name
   ```

   For books: export each child blueprint, then group them with
   `--book "<book name>"`:

   ```sh
   python3 tools/blueprint_storage.py import-string '<bp1>' first --book solar-array
   python3 tools/blueprint_storage.py import-string '<bp2>' second --book solar-array
   ```

To go the other way (library -> in-game), `tools/blueprint_storage.py
export <name>` prints the string. Paste it into Factorio's
**Import string** dialog.

## What remains to reverse-engineer

| Area | Status | Effort to finish |
|------|--------|------------------|
| Header (version, migrations, prototype index, library state) | Verified | -- |
| Top-level blueprint envelope + opaque body capture | Verified | -- |
| Blueprint-book envelope (icons, active slot, nested count) | Open | 1-2 hours of byte-staring on the 'Fleet' object |
| Deconstruction-planner envelope | Open | Need a sample with non-default settings |
| Upgrade-planner envelope | Open | Same |
| Inner blueprint body (entities, tiles, schedules) | Open | This is the bulk; asheiduk's 1.x parser is ~1500 LOC and 2.0 added quality, fluids-as-items, elevated rails, space-platform tiles |
| Re-encoding & writing back to `.dat` | Out of scope for now | Don't even try without all of the above first; the file format must round-trip exactly or the game refuses it. |

## Sources

- [asheiduk/factorio-blueprint-decoder](https://github.com/asheiduk/factorio-blueprint-decoder) -- 1.x decoder, primary reference for stream primitives, count/string encoding, and overall layout.
- [Factorio Forums thread on the format](https://forums.factorio.com/viewtopic.php?t=81662) -- official confirmation that the format is "quasi-random" and may change between releases.
- [Factorio Wiki: Blueprint string format](https://wiki.factorio.com/Blueprint_string_format) -- documents only the deflate+base64 *string* envelope, not the binary library.
- The user's `~/.factorio/blueprint-storage-2.dat` (calibrated against, not redistributed).

## Safety notes

- Never overwrite `blueprint-storage-2.dat` without a timestamped backup. The CLI's `to-game` subcommand is a stub and refuses to run without `--i-have-a-backup`.
- The game may keep a write lock on the file while running. Always close Factorio before any byte-level inspection or copy.
