"""Scraper for https://factorioprints.com/.

factorioprints.com is the older UI sitting on top of the same Firebase
Realtime Database as `factorio.school` (database name `facorio-blueprints`,
typo intentional). The data schema and id format are identical, so this
module reuses the discovery + fetch helpers from `factorio_school` but
records `source_url` against the factorioprints view route, and writes
to its own cache directory `library/external/factorioprints/`.

The split exists for two reasons:
  1. Honest provenance in metadata (`url` should reflect the UI the user
     can open in a browser).
  2. Independent rate limiting if either site adds anti-bot measures.

Both modules share the same upstream Firebase REST endpoints, which is
the only reasonable way to fetch the data short of running a JS engine.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from . import common as _c
from . import factorio_school as _fs

SITE = "factorioprints"
WEB_VIEW_BASE = "https://factorioprints.com/view"


def _web_view_url(bp_id: str) -> str:
    return f"{WEB_VIEW_BASE}/{urllib.parse.quote(bp_id, safe='-_')}"


def _retag(ref: _c.BlueprintRef) -> _c.BlueprintRef:
    return _c.BlueprintRef(
        site=SITE,
        id=ref.id,
        title=ref.title,
        author=ref.author,
        url=_web_view_url(ref.id),
        tags=list(ref.tags),
        fetched_at=ref.fetched_at,
    )


def discover(query: str | None = None, limit: int = 10) -> list[_c.BlueprintRef]:
    """Same Firebase RTDB query as factorio_school, retagged to this site."""
    refs = _fs.discover(query=query, limit=limit)
    return [_retag(r) for r in refs]


def fetch_one(ref_or_id: _c.BlueprintRef | str) -> _c.Blueprint:
    """Fetch and cache under `library/external/factorioprints/`."""
    bp_id = ref_or_id.id if isinstance(ref_or_id, _c.BlueprintRef) else str(ref_or_id)

    cache = _c.lookup_cache(SITE, bp_id)
    if cache.cached:
        bp_string = cache.bp_path.read_text(encoding="utf-8").strip()
        import json as _j
        try:
            meta = _j.loads(cache.json_path.read_text(encoding="utf-8"))
        except _j.JSONDecodeError:
            meta = {}
        return _c.Blueprint(
            site=SITE,
            id=bp_id,
            title=meta.get("title", "(untitled)"),
            author=meta.get("author", ""),
            url=meta.get("url", _web_view_url(bp_id)),
            blueprint_string=bp_string,
            tags=list(meta.get("tags") or []),
            description=meta.get("description", ""),
            fetched_at=meta.get("fetched_at", ""),
            extra=dict(meta.get("extra") or {}),
        )

    # Fetch from the shared Firebase RTDB.
    rl = _c.RateLimiter.get_default()
    payload = rl.fetch_json(_fs._blueprint_url(bp_id))
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected payload for {bp_id}: {type(payload).__name__}")
    bp = _fs._coerce_full_to_blueprint(bp_id, payload)
    # Override provenance to point at factorioprints.
    bp.site = SITE
    bp.url = _web_view_url(bp_id)
    _c.save_blueprint(bp)
    _c.update_manifest(SITE, [_c.BlueprintRef(
        site=bp.site, id=bp.id, title=bp.title, author=bp.author,
        url=bp.url, tags=bp.tags, fetched_at=bp.fetched_at,
    )])
    return bp


__all__ = ["SITE", "discover", "fetch_one"]
