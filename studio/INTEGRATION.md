# How Factudio integrates with FBE

## Decision: same-origin reverse-proxy of the live demo

Factudio mounts the upstream Factorio Blueprint Editor live demo
(<https://fbe.teoxoy.com>, MIT, by teoxoy) under our own origin at `/fbe/`,
then iframes `/fbe/index.html?source=<bp>` next to the build-spec form.

The studio renders **actual Factorio sprites**, not the ASCII fallback,
provided `bash studio/setup_fbe.sh` has been run.

## Why a proxy and not a direct iframe?

The live demo serves a strict CSP:

    content-security-policy: ...; frame-ancestors 'none';

`frame-ancestors 'none'` is a hard browser-enforced refusal to be embedded
in **any** parent frame, regardless of origin or sandbox flags. There is no
client-side workaround.

By proxying through `studio_server.py`, our origin (127.0.0.1) becomes the
*new* origin for the FBE bundle. Our proxy strips the `frame-ancestors`
header on the way out, so the iframe loads.

## Why a proxy and not a vendored build?

We considered building FBE from source via `npm` in `studio/vendor/fbe/`.
That works (Node 20+, ~450 MB of deps, then `vite build`), but it makes
`python3 tools/studio_server.py` no longer the single command the README
promises -- you also need npm, then a sprite-atlas extractor, then a
build step every time upstream ships a 2.0/Space-Age entity. The proxy
avoids all of this: upstream ships, we relay, sprite cache builds itself.

## How the proxy works

`studio/setup_fbe.sh`:

1. Fetches the upstream HTML from <https://fbe.teoxoy.com/> and scrapes the
   hashed Vite bundle filenames (`assets/index-<hash>.{js,css}`,
   `assets/transcoder.<ver>-<hash>.{js,wasm}`).
2. Downloads the entry-point assets: HTML, JS, CSS, transcoder, fonts,
   logos, `data/data.json`. Does **not** download the per-entity sprite
   atlases (~hundreds of small `.basis` textures); those are lazy.
3. Rewrites every absolute URL in the HTML/JS/CSS so `/data/...`,
   `/assets/...`, `/fonts/...`, `/favicon.png` etc. resolve to `/fbe/...`
   instead -- our proxy mount point. Without this, the bundle would try
   to fetch from our root and collide with the studio's own routes.
4. Strips the upstream Cloudflare-insights beacon (no analytics on a
   loopback dev server).

`tools/studio_server.py` adds an `_fbe_load_or_fetch()` helper that:

1. Maps `GET /fbe/<rel>` to `studio/static/fbe/<rel>` on disk.
2. On cache miss, fetches `<FBE_UPSTREAM>/<rel>` (default
   `https://fbe.teoxoy.com`) over `urllib.request`, applies the same URL
   rewrites if the response is HTML/JS/CSS, writes to disk, and serves.
3. Threading: a per-key `Event` deduplicates concurrent fetches of the
   same path so a hot reload of FBE doesn't fan out into N parallel
   downloads of every sprite.
4. Refuses to proxy if `studio/static/fbe/index.html` is missing (i.e.
   `setup_fbe.sh` hasn't been run); returns a 404 with an install hint.

After warm-up, all sprite atlases the user has rendered are local. No
network access is required to re-render the same blueprints.

## Frontend wiring

`studio/index.html` ships an `<iframe id="fbe-frame">` and a `<pre id="ascii-preview">`
side by side in the Preview pane, with a checkbox to toggle between them.

`studio/app.js`:

- Reads `fbe_installed` from `/api/health` once at boot. If false, the
  iframe is hidden and the ASCII fallback is shown along with a banner
  pointing to `studio/setup_fbe.sh`.
- After every successful synthesize / validate, sets the iframe's `src`
  to `/fbe/index.html?source=<urlencoded-bp>`. FBE's
  `getBlueprintOrBookFromSource()` accepts the raw blueprint string
  directly (every Factorio 2.0 string starts with `0`, which is the
  branch FBE takes for raw input).
- Always renders the ASCII preview too, so the report tab is always
  populated; the toggle just hides it visually.

## What about the new-tab "Open in FBE editor" button?

Still works. It opens `https://fbe.teoxoy.com/?source=<bp>` in a new tab.
That's the canonical edit experience (full keyboard shortcuts, save back
to disk, etc.). The iframe is for in-page preview only.

## Cache footprint

- `setup_fbe.sh` seed: ~4 MB on disk
- `data/data.json`: ~2 MB (downloaded by setup)
- Per blueprint: a few KB to a few MB of sprite atlases, depending on
  entity diversity. The smelter_array test case populates ~3 directories
  under `data/__base__/graphics/`. The cache grows monotonically; delete
  `studio/static/fbe/data/` to reset it.

All of `studio/static/fbe/` is gitignored.

## What about Space Age / Quality / Elevated Rails entities?

The upstream live demo at <https://fbe.teoxoy.com> ships only
`__base__` + `__core__` prototypes (121 entities, 214 recipes). It
cannot render Space-Age entities (foundry, recycler, biochamber,
electromagnetic-plant, cryogenic-plant, agricultural-tower,
asteroid-collector, ...) and it applies vanilla parameter values for
entities the user has tweaked through mods (e.g. AdjustableModule
sets beacon `module_slots` 2 -> 5 and `distribution_effectivity`
1.5 -> 3).

`tools/extend_fbe_for_mods.py` solves this. After the seed step
above, `setup_fbe.sh` automatically runs the extension:

1. Loads `specs/data-raw-dump.json` -- the authoritative live dump
   from `factorio --dump-data` of the user's exact enabled mod set.
2. Diffs it against `studio/static/fbe/data/data.json` to find every
   missing entity / item / recipe / fluid.
3. Copies the missing dump entries verbatim into `data.json` (the
   dump uses the same `__source__/...` filename schema FBE expects).
4. For entities that already exist in FBE but have different values
   in the dump, overlays the modded values (`module_slots`,
   `allowed_effects`, `distribution_effectivity`, `crafting_speed`,
   `effect_receiver`, `energy_usage`, ...) onto the FBE entry.
5. Copies the corresponding PNG sprites out of the local Factorio
   install (`~/.local/share/Steam/.../Factorio/data/<source>/`) or
   extracts them from mod zips (`~/.factorio/mods/<mod>.zip`).
6. Patches the FBE JS bundle's `.replace(".png",".basis")` to a
   no-op so PixiJS loads `.png` files directly. (The upstream cloud
   bundle uses Basis Universal for compactness; we don't ship
   `basisu` so we serve raw PNGs. PixiJS supports PNG natively, no
   transcoder needed.)

The extension is **idempotent**. Re-running picks up new prototypes
without duplicating work. Pass `--force` to reset to upstream and
re-extend from scratch (after re-dumping prototypes).

Disk impact: the patched `data.json` grows from ~2 MB to ~4 MB. The
copied sprite tree under `studio/static/fbe/data/__<source>__/`
grows by ~300 MB for the user's full mod set (most of it under
`__space-age__/` and `__quality__/`).

`/api/health` now reports `fbe_extension`, a dict with the sentinel
written into `data.json`:

    {
      "applied": true,
      "version": 2,
      "entities_added": 71,
      "entities_overlaid": 20,
      "items_added": 204,
      "recipes_added": 504,
      "fluids_added": 15,
      "sprites_copied": 1267,
      "sprites_missing": 0,
      "sources": ["base", "core", "space-age", "quality", ...]
    }

`studio/app.js` surfaces this in the FBE-bundle status pill: instead
of "installed" it shows "extended (+71 entities, 20 overlays, +504
recipes from 39 sources)".

Disable the extension at install time with `FBE_NO_MOD_EXTEND=1
bash studio/setup_fbe.sh` if you want strict vanilla rendering for
parity testing against `fbe.teoxoy.com`.

See `studio/EXTENDING.md` for how the sprite extraction works and how
to extend the script for a new mod that adds entities.

## Reachability

`/api/health` reports `fbe_installed` (the local bundle is on disk) and
`fbe_upstream` (the URL we proxy from). The frontend's "FBE bundle"
status pill shows "installed" / "not installed" based on
`fbe_installed`. There is no longer a separate "live demo reachable"
probe -- once the cache is warm, upstream availability doesn't matter.

## Future work

If `fbe.teoxoy.com` ever permanently goes offline before the cache is
warm, the fallback path is documented above (vendor-and-build, Option 2).
Sprite cache from previous runs survives because we never auto-evict.
