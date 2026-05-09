# CLAUDE.md

Guidance for Claude Code sessions working in this repo. Read first.

## Repo purpose

Build an install-aware Factorio blueprint toolkit. The pipeline is:
detect the user's install, dump live prototype data, write human-readable
specs against that data, then drive blueprint-builder agents that emit
valid blueprint strings.

## Where things live

- `specs/data-raw-dump.json` — full Factorio `--dump-data` output for the
  user's enabled mod set. ~28 MB JSON, 250+ prototype categories. This is
  the source of truth for any numeric claim. Do **not** hand-edit it.
- `specs/mod-settings-dump.json` — effective values of all mod settings.
- `docs/` — hand-curated, narrative spec files. See `docs/README.md` for
  the index. Each file is owned by one of agents B/C/D/E.
- `tools/detect_factorio.py` — Python 3, stdlib only. Locates the binary
  and user data dir, parses version + mod list, reports DLC flags.
  CLI: `python3 tools/detect_factorio.py [--human]`. Exits 1 if not found.
- `tools/dump_prototypes.sh` — wraps the detector, runs
  `<binary> --dump-data`, copies the result into `specs/`. Supports
  `--dry-run`.
- `research_notes/` — agent scratch space. Don't treat as authoritative.
- `scripts/` — small helpers (e.g. blueprint encode/decode).
- `validation/` — round-trip tests for blueprint strings.

## Detected install (calibration target)

- Factorio 2.0.76 (Steam, Linux)
- Space Age + Quality + Elevated Rails enabled
- 38 mods enabled (4 first-party + 34 third-party)

Anything that contradicts the dump is wrong by definition.

## Common workflows

### Refresh the prototype dump after a game/mod update

```sh
python3 tools/detect_factorio.py --human    # confirm what's detected
bash    tools/dump_prototypes.sh            # writes specs/data-raw-dump.json
```

The dump command launches the headless Factorio binary; it takes ~30 s
and prints a one-line summary on success. Use `--dry-run` to inspect the
plan without launching the game.

### Look up a prototype value

`specs/data-raw-dump.json` is keyed by prototype category, then by
internal name. For example, `["recipe"]["electronic-circuit"]` holds the
ingredients/results/energy for green circuits, and
`["assembling-machine"]["assembling-machine-3"]` holds crafting speed,
module inventory size, and energy usage.

Prefer `python3 -c "import json; d=json.load(open('specs/data-raw-dump.json')); ..."`
over loading the file into the editor.

### Add a new mod-aware spec

1. Pick a tight scope (one game system).
2. Add `docs/<topic>.md`. Cite values from `specs/data-raw-dump.json`
   rather than from the wiki.
3. Add a one-line entry in `docs/README.md`.
4. If your spec needs derived data (e.g. a flattened recipe table), put
   the generator in `scripts/` and the output in `specs/`.

### Write a blueprint generator

Generators consume the curated docs as Claude context and the JSON dump
as ground truth. Always validate the produced blueprint string with
`validation/` before claiming success.

## Conventions

- Python: stdlib only unless a dependency is unavoidable. Target Python 3.10+.
- Bash: `set -euo pipefail` in every script.
- No emojis in any committed file.
- Prefer reading existing files over creating new ones.
- Don't commit `script-output/` artifacts; the dumper copies what it needs.
- Mod names in `mod-list.json` are case-sensitive and use the exact
  string from the mod portal — match that in any code that filters mods.

## Things to be careful about

- The dump reflects whatever mods are enabled at run time, not what is
  installed. If `mod-list.json` disables a mod, its prototypes will not
  appear in `data-raw-dump.json`.
- Some mods replace base prototypes (e.g. `space-age` overrides several
  base recipes). Always inspect the prototype as it appears in the dump,
  not as it appears in the base game.
- Quality tiers multiply many numeric stats (speed, productivity, module
  effects). The dump reports base values; quality math lives in
  `docs/planets_quality_beacons.md`.
- Blueprint strings depend on prototype names, not display names. Use
  the dump's keys verbatim.

## Don'ts

- Don't write spec content into `README.md` or `CLAUDE.md` — those are
  for project-level guidance only.
- Don't fetch values from the Factorio wiki without cross-checking the
  dump; the wiki lags.
- Don't run the dumper in CI or as a side effect of unrelated work; it
  launches the actual game binary.
