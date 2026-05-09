# factorio_blueprints

A blueprint engineering toolkit for Factorio. The goal is to take a
natural-language spec ("a 60 SPM green-circuit block, beacon-supported,
quality common, on Nauvis") and produce a valid Factorio blueprint string
that drops straight into the game.

To do that reliably we first need a precise, machine-readable model of the
game as it is actually installed on the user's machine — base game,
official DLC, and every loaded mod. Modded prototypes change recipes,
ratios, machine speeds, beacon math, fluidbox geometry, even the rules
for what fits on a logistics network. A spec written against vanilla 1.1
will produce broken blueprints in a 2.0 + Space Age + 30-mod install.

This repo's first job is therefore to be **honest about the user's
install**: detect the binary, dump the live `data.raw` prototype tree,
and write hand-curated documentation that reflects what is actually
loaded.

## Detected install

This repo is currently calibrated against:

- Factorio **2.0.76** (build 84451, linux64, Steam)
- DLC: **Space Age**, **Quality**, **Elevated Rails** (all enabled)
- 38 mods enabled (4 first-party + 34 third-party)

Those are the values reported by `tools/detect_factorio.py`. Re-run it
on a different machine and the same scaffolding will adapt.

## Layout

```
docs/             curated, human-readable specs (one file per topic)
specs/            machine-readable dumps
  data-raw-dump.json     full prototype tree (Factorio --dump-data output)
  mod-settings-dump.json effective mod settings
tools/            scripts to detect the install and refresh the dumps
research_notes/   working notes by individual agents
scripts/          one-off helpers (parsers, converters)
validation/       blueprint round-trip tests
```

## How the multi-agent flow works

The toolkit is built by a small fleet of focused agents, each owning one
slice of the game model:

- **Agent A — skeleton & detection** (this work). README, `CLAUDE.md`,
  install detection, prototype-dump refresher.
- **Agent B — blueprint format.** The wire format: base64 + zlib + JSON,
  entity layout, signal IDs, schedules.
- **Agent C — machines, recipes, ratios.** Crafting speeds, module slots,
  belt throughput, balanced production lines.
- **Agent D — logistics.** Belts, inserters, pipes, bots, train signals,
  circuit network.
- **Agent E — planets, quality, beacons.** Per-planet rules (Vulcanus,
  Fulgora, Gleba, Aquilo), quality tiers, beacon stacking and transmission.

Once the specs are written, blueprint-building agents consume them as
context and call validators in `validation/` before emitting a final
blueprint string. The dump in `specs/data-raw-dump.json` is the source
of truth for any numeric claim a spec wants to make.

## Refreshing the prototype dump

After a game update or a mod change:

```sh
python3 tools/detect_factorio.py --human   # sanity-check what was found
bash    tools/dump_prototypes.sh           # writes specs/data-raw-dump.json
```

The detector is stdlib-only Python 3 and supports Linux (Steam,
Flatpak, snap, `/opt`, `~/.factorio`), macOS (Steam,
`/Applications/factorio.app`) and Windows (Steam, `%APPDATA%\Factorio`).
Use `--dry-run` on the dumper to see what it would do without launching
Factorio.

## Why a live dump?

Factorio's wiki, mod portals and community ratio sheets all drift from
the actual game data. Anything we write a blueprint against has to
match the prototypes Factorio loads at startup. `--dump-data` is the
authoritative source: it runs the full data-stage pipeline (settings,
data, data-updates, data-final-fixes) for the user's exact mod set and
spits out the resulting `data.raw`. We rebuild on top of that.
