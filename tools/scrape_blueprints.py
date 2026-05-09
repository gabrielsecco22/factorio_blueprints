#!/usr/bin/env python3
"""CLI for the polite Factorio blueprint scrapers.

Usage:

    scrape_blueprints.py list <site> [--query Q] [--limit N]
    scrape_blueprints.py fetch <site> <id>
    scrape_blueprints.py crawl <site> [--query Q] [--limit N]
    scrape_blueprints.py status

Sites:
    factorio_school, factorioprints, factoriobin

Cached output (per blueprint) lives under
`library/external/<site>/<id>.bp` (raw blueprint string) and
`library/external/<site>/<id>.json` (metadata).

Run `--help` on any subcommand for details.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

# Make the `tools` package importable when invoked as a script.
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scrapers import common as _c  # noqa: E402

SITES = {
    "factorio_school": "tools.scrapers.factorio_school",
    "factorioprints": "tools.scrapers.factorioprints",
    "factoriobin": "tools.scrapers.factoriobin",
}


def _load_site(name: str):
    if name not in SITES:
        raise SystemExit(
            f"unknown site {name!r}. choose one of: {', '.join(sorted(SITES))}"
        )
    return importlib.import_module(SITES[name])


def _print_robots_decisions(rl: _c.RateLimiter) -> None:
    last = rl.robots.last_decision
    if last:
        url, allowed, rule = last
        verdict = "allowed" if allowed else "denied"
        print(f"[robots.txt] {verdict}: {url}  (rule: {rule})", file=sys.stderr)


def cmd_list(args: argparse.Namespace) -> int:
    site = _load_site(args.site)
    refs = site.discover(query=args.query, limit=args.limit)
    rl = _c.RateLimiter.get_default()
    _print_robots_decisions(rl)
    if args.json:
        print(json.dumps([r.to_dict() for r in refs], indent=2, ensure_ascii=False))
    else:
        if not refs:
            print("(no results)")
        for r in refs:
            print(f"{r.id}\t{r.title}\t{r.url}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    site = _load_site(args.site)
    bp = site.fetch_one(args.id)
    rl = _c.RateLimiter.get_default()
    _print_robots_decisions(rl)
    cache = _c.lookup_cache(site.SITE, bp.id)
    print(f"id:       {bp.id}")
    print(f"title:    {bp.title}")
    print(f"author:   {bp.author}")
    print(f"url:      {bp.url}")
    print(f"tags:     {', '.join(bp.tags) if bp.tags else '(none)'}")
    print(f"bp file:  {cache.bp_path}")
    print(f"json file:{cache.json_path}")
    print(f"bp size:  {cache.bp_path.stat().st_size} bytes")
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    site = _load_site(args.site)
    refs = site.discover(query=args.query, limit=args.limit)
    if not refs:
        print("(nothing to crawl)")
        return 0
    print(f"discovered {len(refs)} refs from {args.site}; fetching...")
    ok = 0
    for r in refs:
        try:
            site.fetch_one(r)
            ok += 1
            print(f"  ok  {r.id}\t{r.title}")
        except _c.RateLimitExceeded as exc:
            print(f"  STOP rate-limit reached: {exc}", file=sys.stderr)
            break
        except Exception as exc:  # noqa: BLE001 - keep crawl resilient
            print(f"  ERR {r.id}\t{type(exc).__name__}: {exc}", file=sys.stderr)
    print(f"crawled {ok}/{len(refs)} blueprints from {args.site}")
    return 0 if ok else 1


def cmd_status(_args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    for site in SITES:
        rows.append(_c.status_for_site(site))
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scrape_blueprints", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="list/search blueprints from a site")
    pl.add_argument("site", choices=sorted(SITES))
    pl.add_argument("--query", "-q", default=None)
    pl.add_argument("--limit", "-n", type=int, default=10)
    pl.add_argument("--json", action="store_true", help="emit JSON instead of TSV")
    pl.set_defaults(func=cmd_list)

    pf = sub.add_parser(
        "fetch",
        help="fetch one blueprint by id",
        description=(
            "Fetch one blueprint by id. Firebase ids start with '-', so prefix with "
            "'--' to stop option parsing, e.g. "
            "'scrape_blueprints.py fetch factorio_school -- -OsBJMo7P-2oKxsEc3oB'."
        ),
    )
    pf.add_argument("site", choices=sorted(SITES))
    pf.add_argument("id")
    pf.set_defaults(func=cmd_fetch)

    pc = sub.add_parser("crawl", help="discover then fetch each result")
    pc.add_argument("site", choices=sorted(SITES))
    pc.add_argument("--query", "-q", default=None)
    pc.add_argument("--limit", "-n", type=int, default=5)
    pc.set_defaults(func=cmd_crawl)

    ps = sub.add_parser("status", help="show cache stats per site")
    ps.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
