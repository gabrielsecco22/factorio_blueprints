# How Factudio integrates with FBE

## Decision: Option A (live demo), open in a new tab

Factudio uses [factorio-blueprint-editor](https://github.com/teoxoy/factorio-blueprint-editor)
hosted at https://fbe.teoxoy.com as its visual editor. We **do not** vendor
the editor source and we **do not** iframe it. Instead, when the user clicks
"Open in FBE editor", Factudio opens a new browser tab at

    https://fbe.teoxoy.com/?source=<urlencoded blueprint string>

and FBE loads the blueprint directly from the URL.

## Why not an iframe?

The first thing we tried. `https://fbe.teoxoy.com/` ships a strict CSP:

```
content-security-policy: default-src 'self'; ...; frame-ancestors 'none';
```

`frame-ancestors 'none'` is a hard browser-enforced refusal to be embedded in
*any* parent frame, regardless of cross-origin policy. There is no escape
hatch short of patching the upstream server. So Option A in its iframe form
is impossible against the live demo.

## Why we still chose Option A (in tab) over Option B/C

Two facts about FBE made the new-tab variant trivially viable:

1. **`?source=` accepts a raw blueprint string.** Confirmed by reading
   `packages/editor/src/core/bpString.ts:186-252` (the
   `getBlueprintOrBookFromSource` function). The branching logic is
   `if (DATA[0] === '0') Promise.resolve(DATA)`, and *every* Factorio 2.0
   blueprint string starts with `0`. So we can pass the entire string through
   the URL bar without going through pastebin/hastebin/etc.
2. **No server work needed.** No 144 MB clone, no `npm install`, no build
   pipeline, no patching to keep current. FBE updates ship to all Factudio
   users automatically.

This trades some interactivity (we can't read state back from FBE
programmatically, since the demo doesn't postMessage to its parent) for
zero hosting + zero maintenance. The "Import from Editor" workflow is therefore
manual: the user copies the modified string out of FBE's UI and pastes it
into Factudio's blueprint-string textarea, then clicks Validate.

## Reachability probe

On page load Factudio fires a `no-cors` `fetch()` against `https://fbe.teoxoy.com/`
and updates the "FBE editor" status pill (top-right of the header) accordingly.
A network failure flips it to "unreachable" and the user can still use the
in-page string preview + ASCII grid.

## What about Option B (vendor as submodule)?

We considered it. The repo is 144 MB on disk (mostly the pre-rendered sprite
assets in `packages/exporter/data`). Building the editor requires Node 20+,
`npm install` (~450 MB of deps), then `vite build`. Running it locally would
need a separate static-asset server because the build output is too large to
inline. None of that is hard, but it makes `python3 tools/studio_server.py`
no longer the single command the project README promises. Reserved as a
fallback if `fbe.teoxoy.com` ever goes offline -- a sparse-checkout of
`packages/editor` + a pre-built bundle from a GitHub Release would suffice.

## What about Option C (fork-and-trim)?

Same trade-off as Option B but with extra ongoing cost: every upstream change
needs to be cherry-picked. Not worth it while the live demo is healthy.

## In-page preview

We render a tiny ASCII grid of the blueprint as a fallback for users who
either don't want to leave the page or whose FBE tab failed to load. The
grid maps one prototype-name pattern to one character (`F` furnace, `A`
assembler, `=` belt, `i` inserter, `S` solar panel, `B` accumulator, `+`
pole, etc.). It's intentionally crude -- enough to confirm "yes, the
synthesis produced *something* shaped right."

## Future work

If `fbe.teoxoy.com` ever goes down, fall back to Option B. The minimal change:

1. `git submodule add https://github.com/teoxoy/factorio-blueprint-editor.git studio/vendor/fbe`
2. Add `studio/vendor/` to `.gitignore` (already done).
3. Build once: `cd studio/vendor/fbe && npm install && npm -w packages/website run build`
4. Have the studio backend serve `studio/vendor/fbe/packages/website/dist/` under
   `/fbe/`, and switch `FBE_BASE` in `app.js` from `https://fbe.teoxoy.com` to
   `/fbe`.

Iframes will work in this layout (same-origin), so the editor can sit next to
the parameters panel without any new-tab dance.
