# library/external/

Local cache of blueprints scraped from public Factorio sharing sites.

This directory is **not** redistributed. Each blueprint here belongs to
its original author and is mirrored solely for personal study so the
toolkit can analyze real-world designs and validate its generators
against them. If you are an author and would like a blueprint removed
from your local cache, simply delete the file.

## Sites currently scraped

| site name (slug) | URL                                | rate limit applied | notes |
| ---------------- | ---------------------------------- | ------------------ | ----- |
| `factorio_school` | https://www.factorio.school/      | 2 s between reqs, 100 reqs/session | SPA. Backed by a public Firebase RTDB at `facorio-blueprints.firebaseio.com`. |
| `factorioprints` | https://factorioprints.com/        | 2 s between reqs, 100 reqs/session | SPA. Same Firebase RTDB as `factorio_school`. We expose two scraper modules so `source_url` reflects the UI the user came in through. |
| `factoriobin`    | https://factoriobin.com/           | 2 s between reqs, 100 reqs/session | Pastebin-style. Server-rendered HTML; raw blueprint string lives on `cdn.factoriobin.com`. No public listing endpoint. |

User-Agent used for every request:
`factorio-blueprints-toolkit/0.1 (+https://github.com/gabrielsecco22/factorio_blueprints)`

`robots.txt` is fetched and consulted before each request. A `Retry-After`
response header is honored on 429/503 with exponential back-off (3 retries).

ToS / robots references:
- factorio.school: <https://www.factorio.school/robots.txt>
- factorioprints.com: <https://factorioprints.com/robots.txt>
- factoriobin.com: <https://factoriobin.com/robots.txt>

At the time of writing, all three sites permit `User-agent: *` with
`Allow: /`. Several Cloudflare-managed bot tokens (Amazonbot, ClaudeBot,
GPTBot, Google-Extended, Bytespider, CCBot) are blanket-disallowed.
Our user-agent is none of those — it identifies as `factorio-blueprints-toolkit`.

## Layout

```
library/external/
  README.md                       (this file - tracked in git)
  factorio_school/
    <id>.bp                       (raw blueprint string, one per file)
    <id>.json                     (metadata: title, author, url, fetched_at, tags, description, extra)
    manifest.json                 (rolling index of every ref we've cached)
  factorioprints/
    <id>.bp
    <id>.json
    manifest.json
  factoriobin/
    <id>.bp
    <id>.json
    manifest.json
```

The contents of each `<site>/` directory are gitignored. Only this
README is checked in.

## Refresh a site cache

```sh
# Discover (no fetch).
python3 tools/scrape_blueprints.py list factorio_school --limit 10

# Fetch one blueprint by id.
# Firebase ids start with '-', which argparse treats as a flag; use '--'.
python3 tools/scrape_blueprints.py fetch factorio_school -- -OsBJMo7P-2oKxsEc3oB

# Discover + fetch each result. Capped at 100 requests per process.
python3 tools/scrape_blueprints.py crawl factorio_school --limit 20

# How much have we cached?
python3 tools/scrape_blueprints.py status
```

## Attribution

Every `<id>.json` file records the original `author`, `source_url`, and
`fetched_at`. When citing a blueprint in any spec, generator output, or
comparison, link back to the `url` field in the metadata. The author
holds the rights to the design; this cache is for **local analysis only**.

If you publish anything derived from a scraped blueprint, credit the
author and link to the original post. Do not republish the blueprint
string without permission.
