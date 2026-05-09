"""Scraper for https://www.factorio.school/.

The site is a SPA that talks to a public Firebase Realtime Database at
`https://facorio-blueprints.firebaseio.com/` (the typo `facorio` is the
real database name; do not "fix" it). The schema, observed live:

    /blueprintSummaries/<id>           summary card (title, image, ts)
    /blueprintSummaries.json?orderBy="lastUpdatedDate"&limitToLast=N
    /blueprintSummaries.json?orderBy="numberOfFavorites"&limitToLast=N
    /blueprints/<id>                    full record incl. blueprintString
    /tags                               flat tag taxonomy

The id is the Firebase push key, e.g. `-OsBJMo7P-2oKxsEc3oB`. The same
database powers `factorioprints.com` (it was forked); we expose two
separate scraper modules so `source_url` reflects which UI the user
came in through.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from . import common as _c

SITE = "factorio_school"
RTDB_BASE = "https://facorio-blueprints.firebaseio.com"
WEB_VIEW_BASE = "https://www.factorio.school/view"


def _summaries_url(*, order_by: str, limit: int) -> str:
    # Firebase REST: orderBy must be a JSON-encoded string.
    qs = urllib.parse.urlencode(
        {"orderBy": f'"{order_by}"', "limitToLast": str(max(1, min(limit, 500)))}
    )
    return f"{RTDB_BASE}/blueprintSummaries.json?{qs}"


def _blueprint_url(bp_id: str) -> str:
    # Firebase keys may start with '-' which is fine in a URL path.
    return f"{RTDB_BASE}/blueprints/{urllib.parse.quote(bp_id, safe='-_')}.json"


def _web_view_url(bp_id: str) -> str:
    return f"{WEB_VIEW_BASE}/{urllib.parse.quote(bp_id, safe='-_')}"


def _coerce_summary_to_ref(bp_id: str, summary: dict[str, Any]) -> _c.BlueprintRef:
    return _c.BlueprintRef(
        site=SITE,
        id=bp_id,
        title=str(summary.get("title", "")).strip() or "(untitled)",
        author="",  # summaries don't carry author; populated by fetch_one.
        url=_web_view_url(bp_id),
        tags=[],
        fetched_at=_c.utc_now_iso(),
    )


def _coerce_full_to_blueprint(bp_id: str, payload: dict[str, Any]) -> _c.Blueprint:
    author = ""
    a = payload.get("author") or {}
    if isinstance(a, dict):
        author = str(a.get("displayName") or a.get("userId") or "").strip()
    bp_string = payload.get("blueprintString") or ""
    if not isinstance(bp_string, str) or not bp_string.strip():
        raise ValueError(f"blueprint {bp_id} has no blueprintString")
    tags_raw = payload.get("tags") or []
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = [str(t) for t in tags_raw]
    desc = str(payload.get("descriptionMarkdown") or "").strip()
    extra: dict[str, Any] = {}
    for k in ("createdDate", "lastUpdatedDate", "numberOfFavorites"):
        if k in payload:
            extra[k] = payload[k]
    img = payload.get("image") or {}
    if isinstance(img, dict) and img.get("id"):
        extra["imgur_id"] = img["id"]
        extra["imgur_type"] = img.get("type")
    return _c.Blueprint(
        site=SITE,
        id=bp_id,
        title=str(payload.get("title") or "(untitled)").strip(),
        author=author,
        url=_web_view_url(bp_id),
        blueprint_string=bp_string.strip(),
        tags=tags,
        description=desc,
        fetched_at=_c.utc_now_iso(),
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover(query: str | None = None, limit: int = 10) -> list[_c.BlueprintRef]:
    """List recent or top blueprints.

    `query`:
      * None or "recent"    -> ordered by lastUpdatedDate desc.
      * "top" / "favorites" -> ordered by numberOfFavorites desc.
      * any other string    -> client-side title substring filter on the
                               most recent 200 (Firebase RTDB has no full
                               text search; we keep this honest).
    """
    rl = _c.RateLimiter.get_default()
    if query is None or query.strip().lower() in {"", "recent", "latest"}:
        url = _summaries_url(order_by="lastUpdatedDate", limit=limit)
        data = rl.fetch_json(url)
    elif query.strip().lower() in {"top", "favorites", "popular"}:
        url = _summaries_url(order_by="numberOfFavorites", limit=limit)
        data = rl.fetch_json(url)
    else:
        url = _summaries_url(order_by="lastUpdatedDate", limit=200)
        data = rl.fetch_json(url)
        needle = query.strip().lower()
        data = {
            k: v
            for k, v in (data or {}).items()
            if isinstance(v, dict) and needle in str(v.get("title", "")).lower()
        }

    if not isinstance(data, dict):
        return []
    items = sorted(
        data.items(),
        key=lambda kv: (kv[1] or {}).get("lastUpdatedDate", 0)
        if isinstance(kv[1], dict)
        else 0,
        reverse=True,
    )
    refs = [_coerce_summary_to_ref(k, v) for k, v in items if isinstance(v, dict)]
    return refs[:limit]


def fetch_one(ref_or_id: _c.BlueprintRef | str) -> _c.Blueprint:
    """Fetch the full blueprint for a ref/id and cache it."""
    bp_id = ref_or_id.id if isinstance(ref_or_id, _c.BlueprintRef) else str(ref_or_id)
    cache = _c.lookup_cache(SITE, bp_id)
    if cache.cached:
        bp_string = cache.bp_path.read_text(encoding="utf-8").strip()
        meta = _read_metadata(cache.json_path)
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

    rl = _c.RateLimiter.get_default()
    payload = rl.fetch_json(_blueprint_url(bp_id))
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected payload for {bp_id}: {type(payload).__name__}")
    bp = _coerce_full_to_blueprint(bp_id, payload)
    _c.save_blueprint(bp)
    _c.update_manifest(SITE, [_c.BlueprintRef(
        site=bp.site, id=bp.id, title=bp.title, author=bp.author,
        url=bp.url, tags=bp.tags, fetched_at=bp.fetched_at,
    )])
    return bp


def _read_metadata(path) -> dict[str, Any]:
    import json as _j
    try:
        return _j.loads(path.read_text(encoding="utf-8"))
    except (OSError, _j.JSONDecodeError):
        return {}


__all__ = ["SITE", "discover", "fetch_one"]
