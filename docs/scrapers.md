# Scrapers

Notes on the polite scrapers that fetch example blueprints from the
public Factorio sharing sites. Code lives in `tools/scrapers/`. Cache
lives in `library/external/<site>/`. CLI is `tools/scrape_blueprints.py`.

## Hard rules (enforced in `tools/scrapers/common.py`)

- Identify ourselves as
  `factorio-blueprints-toolkit/0.1 (+https://github.com/gabrielsecco22/factorio_blueprints)`.
- Consult `robots.txt` per host before every request (`urllib.robotparser`).
- 2 s minimum gap between requests to the same host.
- 100 requests per process, hard cap. `RateLimitExceeded` is raised when hit.
- 30 s per-request timeout.
- Honor `Retry-After` on 429/503 with up to 3 exponential-backoff retries.
- Never re-fetch a blueprint already cached at `library/external/<site>/<id>.bp`.
- Stdlib only.

## factorio.school

URL: <https://www.factorio.school/>. Maintained by raiguard. Modern
React SPA. Replaces FactorioPrints in everything but URL.

**Backend.** The SPA talks straight to a public Firebase Realtime
Database at <https://facorio-blueprints.firebaseio.com/> (the typo
`facorio` is the actual database name; do not "fix" it). The API key
in the JS bundle (`AIzaSyAcZJ7hGfxYKhkGHJwAnsLS3z5Tg9kWw2s`) is a
public Firebase web key, not a credential — Firebase enforces auth at
the database rules layer, not via this key. The RTDB exposes any
non-auth-restricted path under `/<path>.json`.

Endpoints we use:

| endpoint | purpose |
| --- | --- |
| `/blueprintSummaries.json?orderBy="lastUpdatedDate"&limitToLast=N` | latest N posts (summary card data) |
| `/blueprintSummaries.json?orderBy="numberOfFavorites"&limitToLast=N` | top N posts |
| `/blueprintSummaries.json?shallow=true` | flat list of every blueprint id (use sparingly: ~480 KB, ~80k ids) |
| `/blueprints/<id>.json` | full record incl. `blueprintString`, `author.{displayName,userId}`, `tags[]`, `descriptionMarkdown`, `image.{id,type}`, `createdDate`, `lastUpdatedDate`, `numberOfFavorites` |
| `/tags.json?shallow=true` | flat tag taxonomy (`production`, `belt`, `combat`, `planets`, `train`, `power`, ...) |

Tag values look like `/version/2,0/`, `/mods/space-age/`,
`/production/electronic circuit (green)/`. Useful for filtering Space
Age-only or 2.0-only posts.

The Firebase id format is the standard push key: ~20 chars, leading
`-`, sortable by creation time. Treat as opaque.

**Anti-bot.** None observed. The `robots.txt` blanket-disallows a list
of LLM-crawler tokens (ClaudeBot, GPTBot, etc.) but our user-agent is
not one of them; the `User-agent: *` block is `Allow: /`.

**Data hygiene notes.**
- Some posts are blueprint **books-of-books**. The `blueprintString`
  decodes to a `{"blueprint_book": {...}}` envelope — see
  `docs/blueprint_format.md`. Our scraper saves the string verbatim;
  downstream consumers must handle both `blueprint` and
  `blueprint_book` envelopes.
- A handful of older entries store images on Imgur; the `image.id`
  field references an Imgur hash. We record it under `extra.imgur_id`
  but never download it.
- Tag normalization is loose: case + slashes vary between posts. If
  you index tags, lowercase + collapse repeated slashes first.

## factorioprints.com

URL: <https://factorioprints.com/>. Older UI, still active. Backed by
the **same** Firebase RTDB as factorio.school. The schema, ids, and
query mechanics are identical, so `tools/scrapers/factorioprints.py`
imports the helpers from `factorio_school.py` rather than duplicating
the URL builders.

We expose two scraper modules instead of one to keep provenance honest:
the `url` field in cached metadata points at the UI the user came in
through, and per-host rate limiting / cache directories are independent
in case either site adds anti-bot measures or diverges from the shared
backend.

**Anti-bot.** None observed. Same robots.txt policy as factorio.school
(both sit behind Cloudflare with the same bot-token disallows).

## factoriobin.com

URL: <https://factoriobin.com/>. Pastebin-style: each post is one
shareable blueprint string under `/post/<id>`. No public listing,
no search, no API.

**Discovery.** There is no listing endpoint. `discover()` returns the
canonical demo post (`/post/demo`) by default, or any explicit ids /
URLs the caller supplies via `--query`. Real-world usage will be
"someone linked me a factoriobin post; mirror it".

**Fetch flow.**
1. `GET /post/<id>` returns server-rendered HTML (Hono framework).
2. Parse with stdlib `html.parser`:
   - `<title>` -> "post title - inner title - FactorioBin"
   - first `<span class="frt ...">` -> the blueprint title
   - second `frt` span -> description (if any)
   - `Posted by <span class="user-link ...">AUTHOR</span>` -> author
   - all `<a href="https://cdn.factoriobin.com/perma/bp/.../*.txt">` ->
     direct CDN links to the raw blueprint string(s).
3. `GET` the first CDN link. The body is the blueprint string verbatim.

A `_CDN_BP_RE` regex backs up the parser in case the HTML structure
shifts.

**Books.** A factoriobin "post" can be a single blueprint, a book, or
a book-of-books. When it's a book, the post page lists multiple CDN
URLs (one per top-level entry plus often one for the whole book). We
save the first URL as the canonical blueprint and record the rest in
`extra.extra_blueprint_urls`. Callers who want the components can
iterate.

**Anti-bot.** None observed. The Cloudflare bot-management JS beacon
runs but it does not block plain `urllib` requests at our rate. If
that changes, the parser still works on cached HTML.

**Data hygiene notes.**
- Anonymous posts have author span text "Anonymous"; verified posts
  show a checkmark icon. We just take the literal author text.
- Demo post id is the literal string `demo`. Real ids are mixed-case
  alnum strings (e.g. `demo-da5ygo` appears in the CDN path but the
  post id itself is just `demo`).
- The CDN URL contains the post id pre-fixed by the first letters of
  the id for sharding (`/perma/bp/d/e/demo-da5ygo/...`). We do not
  reconstruct CDN URLs from ids; we only use URLs the post page hands
  us.

## Stub: factoriobp.com

DNS does not resolve from this network, so no scraper module is shipped.
Reserve the slug `factoriobp` for a future module if the site comes
back. Adding it would mirror the factoriobin shape (HTML scraping +
direct blueprint download).

## Verifying a scraper

For each shipped site:

```sh
python3 tools/scrape_blueprints.py list <site> --limit 3
python3 tools/scrape_blueprints.py fetch <site> <id>
python3 tools/blueprint_codec.py decode "$(cat library/external/<site>/<id>.bp)" >/dev/null
```

The codec command must exit 0 — that proves the cached `.bp` is a
valid Factorio 2.0 blueprint string (or book).

`validation/test_scrapers.py` runs the same proof on every shipped
scraper behind `FACTORIO_SCRAPER_LIVE=1`, plus mocked-HTTP tests that
do not touch the network.
