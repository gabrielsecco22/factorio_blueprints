"""Scraper for https://factoriobin.com/.

factoriobin is a pastebin-style host: each post lives at `/post/<id>` and
the raw blueprint string sits on `cdn.factoriobin.com` as a text file.
There is no public listing API, so `discover()` is intentionally limited:

  * If `query` looks like a comma/space separated list of post ids, those
    are returned as refs.
  * Otherwise we return the canonical demo post (`/post/demo`) so the
    rest of the toolkit (CLI, tests) can exercise the scraper without
    needing curated ids.

`fetch_one()` does the real work:
  1. GET `https://factoriobin.com/post/<id>` (server-rendered HTML).
  2. Parse out the post title, author, and the cdn.factoriobin.com link
     to the raw `.txt` blueprint string.
  3. GET that link and save the string + metadata to the local cache.

Books-of-books on factoriobin can list multiple downloadable strings;
we save the first one (`fbin-<id>-0.txt`). The metadata records the
total number of strings discovered so callers can decide whether to
fetch the others.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from . import common as _c

SITE = "factoriobin"
WEB_BASE = "https://factoriobin.com"
POST_URL_TEMPLATE = WEB_BASE + "/post/{id}"
DEMO_ID = "demo"


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


_CDN_BP_RE = re.compile(
    r'https://cdn\.factoriobin\.com/perma/bp/[^"\'<> ]+\.txt'
)


class _PostHTMLParser(HTMLParser):
    """Pulls title / author / blueprint links out of a /post/<id> page.

    The HTML is server-rendered Bootstrap, so structure is stable.
    Hooks of interest:
      - <title>...FactorioBin</title>
      - <span class="frt ...">TITLE</span>           (first one is post title)
      - Posted by <span class="user-link ...">AUTHOR</span>
      - <a href="https://cdn.factoriobin.com/perma/bp/...txt">             (each blueprint)
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None  # from <title> tag
        self.frt_titles: list[str] = []
        self.author: str | None = None
        self.blueprint_urls: list[str] = []

        self._in_title_tag = False
        self._in_frt_span_depth = 0
        self._frt_buf: list[str] = []
        self._in_user_link_span = False
        self._user_link_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrd = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title_tag = True
            self._frt_buf = []  # piggyback buffer
            return
        if tag == "span":
            classes = attrd.get("class", "").split()
            if "frt" in classes and self._in_frt_span_depth == 0:
                self._in_frt_span_depth = 1
                self._frt_buf = []
                return
            if self._in_frt_span_depth:
                self._in_frt_span_depth += 1
            if "user-link" in classes and self.author is None:
                self._in_user_link_span = True
                self._user_link_buf = []
                return
        if tag == "a":
            href = attrd.get("href", "")
            if href.startswith("https://cdn.factoriobin.com/perma/bp/") and href.endswith(".txt"):
                if href not in self.blueprint_urls:
                    self.blueprint_urls.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title_tag:
            self._in_title_tag = False
            txt = "".join(self._frt_buf).strip()
            self.title = txt
            self._frt_buf = []
            return
        if tag == "span":
            if self._in_frt_span_depth:
                self._in_frt_span_depth -= 1
                if self._in_frt_span_depth == 0:
                    txt = "".join(self._frt_buf).strip()
                    if txt and txt not in self.frt_titles:
                        self.frt_titles.append(txt)
                    self._frt_buf = []
                return
            if self._in_user_link_span:
                self._in_user_link_span = False
                txt = "".join(self._user_link_buf).strip()
                if txt:
                    self.author = txt
                self._user_link_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_title_tag:
            self._frt_buf.append(data)
        if self._in_frt_span_depth:
            self._frt_buf.append(data)
        if self._in_user_link_span:
            self._user_link_buf.append(data)


def _parse_post_html(html_text: str) -> dict[str, Any]:
    p = _PostHTMLParser()
    p.feed(html_text)
    p.close()

    # If the parser missed CDN urls (e.g. odd whitespace), fall back to regex.
    urls: list[str] = list(p.blueprint_urls)
    for m in _CDN_BP_RE.finditer(html_text):
        u = m.group(0)
        if u not in urls:
            urls.append(u)

    # The <title> tag is "<post title> - <inner title> - FactorioBin" or
    # "<post title> - FactorioBin". The first frt span is the inner title.
    raw_title = p.title or ""
    raw_title = re.sub(r"\s*-\s*FactorioBin\s*$", "", raw_title).strip()
    inner_title = p.frt_titles[0] if p.frt_titles else ""
    description = p.frt_titles[1] if len(p.frt_titles) > 1 else ""

    return {
        "post_title": raw_title,
        "inner_title": inner_title,
        "description": description,
        "author": p.author or "",
        "blueprint_urls": urls,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover(query: str | None = None, limit: int = 10) -> list[_c.BlueprintRef]:
    """Return refs for any explicit ids in `query`, else just the demo post.

    factoriobin has no public listing endpoint. Callers who already know
    post ids (e.g. from forum links) should pass them as a comma- or
    whitespace-separated string.
    """
    ids: list[str] = []
    if query:
        # Accept either bare ids or full URLs.
        for token in re.split(r"[\s,]+", query.strip()):
            if not token:
                continue
            if token.startswith("http"):
                m = re.search(r"/post/([A-Za-z0-9_-]+)", token)
                if m:
                    ids.append(m.group(1))
            else:
                ids.append(token)
    if not ids:
        ids = [DEMO_ID]

    refs = []
    for bp_id in ids[:limit]:
        refs.append(_c.BlueprintRef(
            site=SITE,
            id=bp_id,
            title=f"factoriobin post {bp_id}",
            author="",
            url=POST_URL_TEMPLATE.format(id=urllib.parse.quote(bp_id, safe="-_")),
            tags=[],
            fetched_at=_c.utc_now_iso(),
        ))
    return refs


def fetch_one(ref_or_id: _c.BlueprintRef | str) -> _c.Blueprint:
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
            url=meta.get("url", POST_URL_TEMPLATE.format(id=bp_id)),
            blueprint_string=bp_string,
            tags=list(meta.get("tags") or []),
            description=meta.get("description", ""),
            fetched_at=meta.get("fetched_at", ""),
            extra=dict(meta.get("extra") or {}),
        )

    rl = _c.RateLimiter.get_default()
    post_url = POST_URL_TEMPLATE.format(id=urllib.parse.quote(bp_id, safe="-_"))
    html_text = rl.fetch_text(post_url, accept="text/html")
    parsed = _parse_post_html(html_text)
    if not parsed["blueprint_urls"]:
        raise ValueError(f"no blueprint string found on {post_url}")

    bp_url = parsed["blueprint_urls"][0]
    bp_string = rl.fetch_text(bp_url, accept="text/plain").strip()
    if not bp_string:
        raise ValueError(f"empty blueprint string at {bp_url}")

    title = parsed["inner_title"] or parsed["post_title"] or f"factoriobin/{bp_id}"
    bp = _c.Blueprint(
        site=SITE,
        id=bp_id,
        title=title,
        author=parsed["author"] or "anonymous",
        url=post_url,
        blueprint_string=bp_string,
        tags=[],
        description=parsed["description"],
        fetched_at=_c.utc_now_iso(),
        extra={
            "post_title": parsed["post_title"],
            "blueprint_url": bp_url,
            "extra_blueprint_urls": parsed["blueprint_urls"][1:],
        },
    )
    _c.save_blueprint(bp)
    _c.update_manifest(SITE, [_c.BlueprintRef(
        site=bp.site, id=bp.id, title=bp.title, author=bp.author,
        url=bp.url, tags=bp.tags, fetched_at=bp.fetched_at,
    )])
    return bp


__all__ = ["SITE", "DEMO_ID", "discover", "fetch_one", "_parse_post_html"]
