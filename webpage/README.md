# Factorio Blueprint Tools Catalog (webpage)

Static, single-page catalog of modern Factorio blueprint editors,
calculators, renderers, and helper mods. No build system, no frameworks,
no CDN dependencies — open the page directly with a tiny local server.

## Run it locally

```sh
python3 webpage/build.py                              # validate + stamp
python3 -m http.server 8000 -d webpage                # serve it
# then open http://localhost:8000/
```

Or in one shot:

```sh
python3 webpage/build.py --serve --port 8000
```

`build.py` uses only the Python standard library.

## How the data is sourced

Two sibling agents populate JSON files under `webpage/data/`:

| File | Contents |
| --- | --- |
| `oss_tools.json` | open-source tool records |
| `community_tools.json` | community-recommended tool records |
| `community_sentiment_oss.json` | optional sentiment payload |
| `oss_tools.notes.md` | research notes for the OSS list |
| `community_tools.notes.md` | research notes for the community list |
| `last_built.json` | timestamp + record counts (written by `build.py`) |

If either tool-list JSON is missing or malformed, `app.js` falls back
to a small hard-coded seed dataset (FBE, FactorioLab, Kirk McDonald,
factorio-draftsman, Helmod, FactorioBin, plus a few community
recommendations) and shows an info banner. The page therefore renders
even on a fresh checkout.

## Data record schema

Each record in `oss_tools.json` / `community_tools.json` should look
like:

```json
{
  "id": "factoriolab",
  "name": "FactorioLab",
  "category": "calculator",
  "description": "Recipe and production-rate calculator ...",
  "homepage": "https://factoriolab.github.io/",
  "demo": "https://factoriolab.github.io/",
  "source": "https://github.com/factoriolab/factoriolab",
  "open_source": true,
  "ready_2_0": true,
  "space_age": true,
  "maintained": "active",
  "last_commit": "2025-09-01",
  "notes": "optional free-form text"
}
```

Required fields: `id`, `name`, `homepage`, `category`, `description`.

`category` must be one of:

- `visual-editor`
- `calculator`
- `string-paste`
- `renderer`
- `in-game-mod`
- `library`

`maintained` may be `active`, `aging`, `stale`, or `unknown`. If
omitted, the page derives a status from `last_commit` (an ISO date
string): under 12 months = active, 12-24 months = aging, older or
missing = stale/unknown.

The top-level shape can be either a JSON array or
`{"tools": [...]}` — both are accepted by `build.py` and `app.js`.

## Adding a new tool

1. Append a record to `webpage/data/oss_tools.json` or
   `webpage/data/community_tools.json`.
2. Run `python3 webpage/build.py` to revalidate and refresh the
   "data last refreshed" stamp.
3. Reload the page.

Records that appear in both files are deduplicated by `id`; the OSS
list wins.

## Page features

- Filter chips for category and compatibility flags (2.0, Space Age,
  open source). Multi-select.
- Filter state is persisted in the URL hash (`#category=...&flags=...`)
  so links to a filtered view are shareable.
- Sort order: 2.0 + Space Age ready first, then maintained-active, then
  alphabetical.
- Status dot per card: green / yellow / gray for active / aging /
  stale-or-unknown.
- Dark theme, system-ui font, mobile-friendly grid.

## Hosting on GitHub Pages

The contents of `webpage/` are static and self-contained, so the
catalog is gh-pages-ready:

1. Copy or `git subtree push` the `webpage/` directory onto the
   `gh-pages` branch root.
2. Enable Pages for the `gh-pages` branch in the repository settings.
3. Re-run `python3 webpage/build.py` before each push to refresh the
   timestamp.

No analytics, no tracking, no remote fonts.
