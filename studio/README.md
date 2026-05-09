# Factudio - Factorio Blueprint Studio

A small web app on top of the harness that lets you fill in a build spec,
generate a blueprint, see a preview, and open the result in the
[FBE](https://fbe.teoxoy.com/) editor in a new tab.

## Run it

```sh
python3 tools/studio_server.py --port 8766
```

Then open http://127.0.0.1:8766/ in a browser.

The server is stdlib only (no pip installs) and binds to `127.0.0.1` only --
it deliberately refuses to listen on the network. Press Ctrl-C to stop;
because we set `SO_REUSEADDR`, you can immediately re-bind on the same port.

## Layout

```
studio/
|-- README.md           This file.
|-- INTEGRATION.md      How and why we integrated FBE the way we did.
|-- index.html          Studio page (parameters left, editor pane right).
|-- styles.css          Dark theme matching webpage/styles.css.
`-- app.js              Vanilla JS, talks to /api/*.

tools/
`-- studio_server.py    Stdlib HTTP server. Loopback-only.
```

## What you can do

- Fill in a build spec (target item, machine, fuel, belt tier, research, quality, mod set).
- Click **Generate** -> the harness runs, the blueprint string + a markdown
  report appear in the right pane.
- Click **Open in FBE editor** -> a new tab opens at
  `https://fbe.teoxoy.com/?source=<your bp string>`. The string travels via
  the URL only; nothing is sent to FBE's backend.
- Edit in FBE, copy the modified string out (FBE's "Generate string" button),
  paste it into Factudio's "Blueprint string" tab, then click **Validate** to
  re-check it and re-render the rate calculator.
- Click **Save to library** to persist the current string into
  `library/personal/` via the existing `LibraryStore` (one `.bp` file).

## Endpoints

| Method | Path             | Purpose                                                 |
| ------ | ---------------- | ------------------------------------------------------- |
| GET    | `/`              | Serves `studio/index.html` and friends.                 |
| GET    | `/api/health`    | Backend status, harness availability, mod-list count.   |
| GET    | `/api/recipes`   | All recipes with ingredients + results + category.      |
| GET    | `/api/machines`  | All assembler-style machines + their crafting categories. |
| GET    | `/api/belts`     | Transport belts only (no splitters/underground).        |
| GET    | `/api/items`     | All items, with `from_mod` for mod-compat.              |
| GET    | `/api/quality`   | Quality tiers (normal..legendary).                      |
| GET    | `/api/research`  | Research effect names a planner cares about.            |
| GET    | `/api/library`   | Saved blueprints in `library/personal/`.                |
| POST   | `/api/synthesize`| BuildSpec JSON -> blueprint string + report + warnings. |
| POST   | `/api/validate`  | Decode a string, re-encode to round-trip-check, mod-compat the entities. |
| POST   | `/api/save`      | Write a string into the library.                        |

All errors come back as `{"ok": false, "error": "..."}`. All successes are JSON.

## Mod compatibility

When you target an item that needs a mod you don't have enabled (per
`~/.factorio/mods/mod-list.json`), `/api/synthesize` returns:

```json
{
  "warnings": [
    {"level": "error",
     "message": "target 'molten-iron' requires mod 'space-age' which is not enabled in mod-list.json",
     "suggested_substitute": "iron-plate"}
  ],
  "mod_compat": {
    "required": ["space-age", "base"],
    "available": ["base", "core", "quality", ...],
    "missing": ["space-age"]
  }
}
```

The substitution table is intentionally tiny -- it covers the most common
"oh I don't have Space Age" cases. Extend `_suggest_substitute` in
`tools/studio_server.py` if you find more.

## Why FBE in a new tab and not iframed?

`fbe.teoxoy.com` ships a `frame-ancestors 'none'` Content Security Policy
header that blocks all iframing. We open it in a new tab via the documented
`?source=<bp>` URL parameter instead, which works for any 2.0 blueprint
string (they all start with `0`, which FBE treats as a literal string). See
`INTEGRATION.md` for the full rationale and the fallback plan.

## Testing it from the shell

```sh
# 1. Start the server.
python3 tools/studio_server.py --port 8766 &

# 2. Health check.
curl -s http://127.0.0.1:8766/api/health | python3 -m json.tool

# 3. Synthesize.
curl -s -X POST http://127.0.0.1:8766/api/synthesize \
  -H "Content-Type: application/json" \
  -d '{"kind":"smelter_array","target":"iron-plate","machine_count":12,
       "machine_choice":"stone-furnace","fuel":"coal",
       "inserter_tier":"burner-inserter"}' | python3 -m json.tool | head -40

# 4. Open in browser.
xdg-open http://127.0.0.1:8766/
```
