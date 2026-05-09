#!/usr/bin/env python3
"""Tests for `tools/scrapers/`.

Two tiers:

  1. Always-on, mocked HTTP. We monkeypatch `urllib.request.urlopen`
     inside `tools.scrapers.common` so no network is touched. These
     verify the parsing of each scraper.

  2. Live smoke tests gated behind `FACTORIO_SCRAPER_LIVE=1`. Each
     shipped scraper fetches one real blueprint and asserts:

       - the cache `.bp` and `.json` files exist and are non-empty,
       - the `.bp` contents decode via `tools/blueprint_codec.py`,
       - metadata records `author`, `url`, `fetched_at`.

Run:

    python3 validation/test_scrapers.py
    FACTORIO_SCRAPER_LIVE=1 python3 validation/test_scrapers.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from typing import Any

# Make the repo importable as a package root.
_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools import blueprint_codec  # noqa: E402
from tools.scrapers import common as _c  # noqa: E402
from tools.scrapers import factorio_school as _fs  # noqa: E402
from tools.scrapers import factorioprints as _fp  # noqa: E402
from tools.scrapers import factoriobin as _fb  # noqa: E402

LIVE = os.environ.get("FACTORIO_SCRAPER_LIVE") == "1"

# A tiny real blueprint string we can roundtrip without touching the network.
_TINY_BP = blueprint_codec._KNOWN_STRING


# ---------------------------------------------------------------------------
# Mocked HTTP helpers
# ---------------------------------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, body: bytes, content_type: str = "application/octet-stream",
                 headers: dict[str, str] | None = None) -> None:
        self._body = body
        self._headers = headers or {}
        self.headers = _Headers(content_type, self._headers)

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Headers:
    def __init__(self, content_type: str, extras: dict[str, str]) -> None:
        self._ct = content_type
        self._items = dict(extras)
        self._items.setdefault("Content-Type", content_type)

    def get_content_type(self) -> str:
        return self._ct

    def get(self, key: str, default: Any = None) -> Any:
        return self._items.get(key, default)

    def items(self):
        return self._items.items()


def _make_urlopen(routes: dict[str, _FakeHTTPResponse]):
    """Build a fake urlopen that returns a canned response per URL.

    URLs are matched by exact string OR by `url.startswith(key)` so
    callers can register a prefix like `https://host/api/`.
    """

    def _fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url in routes:
            return routes[url]
        for k, resp in routes.items():
            if url.startswith(k):
                return resp
        raise AssertionError(f"unexpected URL in mocked test: {url!r}")

    return _fake_urlopen


def _reset_rate_limiter(tmp_root: Path) -> None:
    """Force a fresh RateLimiter and redirect the cache to a tmp dir."""
    _c.RateLimiter._default = _c.RateLimiter(min_delay_s=0.0)
    # Patch library_root to a tmp dir for the duration of the test.
    _c.library_root = lambda: tmp_root  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# robots.txt + RateLimiter unit tests
# ---------------------------------------------------------------------------


_ROBOTS_ALLOW_ALL = b"User-agent: *\nAllow: /\n"
_ROBOTS_DENY_ALL = b"User-agent: *\nDisallow: /\n"


class TestRateLimiter(unittest.TestCase):
    def test_robots_allows_when_allow_all(self) -> None:
        routes = {
            "https://example.test/robots.txt": _FakeHTTPResponse(_ROBOTS_ALLOW_ALL, "text/plain"),
            "https://example.test/data.json": _FakeHTTPResponse(b'{"ok":true}', "application/json"),
        }
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            rl = _c.RateLimiter(min_delay_s=0.0)
            data = rl.fetch_json("https://example.test/data.json")
        self.assertEqual(data, {"ok": True})
        self.assertEqual(rl.requests_made, 1)
        self.assertTrue(rl.robots.last_decision[1])  # allowed

    def test_robots_blocks_when_disallow_all(self) -> None:
        routes = {
            "https://example.test/robots.txt": _FakeHTTPResponse(_ROBOTS_DENY_ALL, "text/plain"),
        }
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            rl = _c.RateLimiter(min_delay_s=0.0)
            with self.assertRaises(_c.RobotsDisallowed):
                rl.fetch("https://example.test/x")

    def test_session_cap_enforced(self) -> None:
        routes = {
            "https://example.test/robots.txt": _FakeHTTPResponse(_ROBOTS_ALLOW_ALL, "text/plain"),
            "https://example.test/p": _FakeHTTPResponse(b"ok", "text/plain"),
        }
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            rl = _c.RateLimiter(min_delay_s=0.0, max_requests=2)
            rl.fetch("https://example.test/p")
            rl.fetch("https://example.test/p")
            with self.assertRaises(_c.RateLimitExceeded):
                rl.fetch("https://example.test/p")


# ---------------------------------------------------------------------------
# factorio.school (mocked)
# ---------------------------------------------------------------------------


_FS_BP_OBJ = {
    "author": {"displayName": "Test Author", "userId": "uid-1"},
    "blueprintString": _TINY_BP,
    "createdDate": 1700000000000,
    "lastUpdatedDate": 1700000001000,
    "numberOfFavorites": 7,
    "tags": ["/version/2,0/", "/mods/space-age/"],
    "descriptionMarkdown": "small example",
    "image": {"id": "abcd", "type": "image/png"},
    "title": "Tiny Pole",
}


def _fs_routes(bp_id: str) -> dict[str, _FakeHTTPResponse]:
    summaries = {
        bp_id: {
            "title": "Tiny Pole",
            "lastUpdatedDate": 1700000001000,
            "numberOfFavorites": 7,
            "imgurId": "abcd",
            "imgurType": "image/png",
        }
    }
    return {
        "https://facorio-blueprints.firebaseio.com/robots.txt": _FakeHTTPResponse(
            _ROBOTS_ALLOW_ALL, "text/plain"
        ),
        "https://facorio-blueprints.firebaseio.com/blueprintSummaries.json":
            _FakeHTTPResponse(
                json.dumps(summaries).encode("utf-8"), "application/json"
            ),
        f"https://facorio-blueprints.firebaseio.com/blueprints/{bp_id}.json":
            _FakeHTTPResponse(
                json.dumps(_FS_BP_OBJ).encode("utf-8"), "application/json"
            ),
    }


class TestFactorioSchoolMocked(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _reset_rate_limiter(Path(self.tmp.name))

    def test_discover_recent_parses_summaries(self) -> None:
        bp_id = "-OabcDEF1234567890ab"
        routes = _fs_routes(bp_id)
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            refs = _fs.discover(query="recent", limit=5)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].id, bp_id)
        self.assertEqual(refs[0].title, "Tiny Pole")
        self.assertEqual(refs[0].url, f"https://www.factorio.school/view/{bp_id}")
        self.assertEqual(refs[0].site, "factorio_school")

    def test_fetch_one_caches_and_decodes(self) -> None:
        bp_id = "-OabcDEF1234567890ab"
        routes = _fs_routes(bp_id)
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            bp = _fs.fetch_one(bp_id)
        self.assertEqual(bp.author, "Test Author")
        self.assertEqual(bp.tags, ["/version/2,0/", "/mods/space-age/"])
        self.assertTrue(bp.fetched_at.endswith("Z"))
        # Cache files written.
        cache = _c.lookup_cache("factorio_school", bp_id)
        self.assertTrue(cache.cached)
        # Round-trip via codec.
        decoded = blueprint_codec.decode(cache.bp_path.read_text().strip())
        self.assertIn("blueprint", decoded)


# ---------------------------------------------------------------------------
# factorioprints (mocked) - same backend, retagged
# ---------------------------------------------------------------------------


class TestFactorioPrintsMocked(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _reset_rate_limiter(Path(self.tmp.name))

    def test_discover_retags_url(self) -> None:
        bp_id = "-OabcDEF1234567890ab"
        routes = _fs_routes(bp_id)
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            refs = _fp.discover(limit=5)
        self.assertEqual(refs[0].site, "factorioprints")
        self.assertEqual(refs[0].url, f"https://factorioprints.com/view/{bp_id}")

    def test_fetch_one_writes_to_factorioprints_dir(self) -> None:
        bp_id = "-OabcDEF1234567890ab"
        routes = _fs_routes(bp_id)
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(routes)):
            bp = _fp.fetch_one(bp_id)
        self.assertEqual(bp.site, "factorioprints")
        self.assertEqual(bp.url, f"https://factorioprints.com/view/{bp_id}")
        cache = _c.lookup_cache("factorioprints", bp_id)
        self.assertTrue(cache.cached)
        # Should NOT have written to factorio_school dir.
        other = _c.lookup_cache("factorio_school", bp_id)
        self.assertFalse(other.has_bp)


# ---------------------------------------------------------------------------
# factoriobin (mocked)
# ---------------------------------------------------------------------------


_FB_HTML = """<!DOCTYPE html><html><head>
<title>My Cool Post - My Inner Title - FactorioBin</title>
</head><body>
<div>Posted by <span class="user-link not-anonymous">CoolAuthor</span></div>
<div>
  <div><span class="frt ">My Inner Title</span></div>
  <div><span class="frt ml ">A description of the build.</span></div>
  <a class="btn btn-primary" href="https://cdn.factoriobin.com/perma/bp/a/b/abcde-xyz/fbin-abcde-0.txt">View</a>
  <a class="btn btn-primary" href="https://cdn.factoriobin.com/perma/bp/a/b/abcde-xyz/fbin-abcde-1.txt">View</a>
</div></body></html>"""


def _fb_routes() -> dict[str, _FakeHTTPResponse]:
    return {
        "https://factoriobin.com/robots.txt": _FakeHTTPResponse(_ROBOTS_ALLOW_ALL, "text/plain"),
        "https://cdn.factoriobin.com/robots.txt": _FakeHTTPResponse(_ROBOTS_ALLOW_ALL, "text/plain"),
        "https://factoriobin.com/post/abcde": _FakeHTTPResponse(_FB_HTML.encode("utf-8"), "text/html"),
        "https://cdn.factoriobin.com/perma/bp/a/b/abcde-xyz/fbin-abcde-0.txt":
            _FakeHTTPResponse(_TINY_BP.encode("utf-8"), "text/plain"),
    }


class TestFactorioBinMocked(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        _reset_rate_limiter(Path(self.tmp.name))

    def test_html_parser_extracts_fields(self) -> None:
        parsed = _fb._parse_post_html(_FB_HTML)
        self.assertEqual(parsed["post_title"], "My Cool Post - My Inner Title")
        self.assertEqual(parsed["inner_title"], "My Inner Title")
        self.assertEqual(parsed["description"], "A description of the build.")
        self.assertEqual(parsed["author"], "CoolAuthor")
        self.assertEqual(len(parsed["blueprint_urls"]), 2)
        self.assertTrue(parsed["blueprint_urls"][0].endswith("fbin-abcde-0.txt"))

    def test_discover_default_returns_demo(self) -> None:
        refs = _fb.discover()
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].id, "demo")

    def test_discover_with_explicit_ids(self) -> None:
        refs = _fb.discover(query="abc def", limit=10)
        self.assertEqual([r.id for r in refs], ["abc", "def"])

    def test_discover_strips_urls(self) -> None:
        refs = _fb.discover(query="https://factoriobin.com/post/xyz123")
        self.assertEqual(refs[0].id, "xyz123")

    def test_fetch_one_caches_and_decodes(self) -> None:
        with mock.patch("tools.scrapers.common.urllib.request.urlopen",
                        side_effect=_make_urlopen(_fb_routes())):
            bp = _fb.fetch_one("abcde")
        self.assertEqual(bp.author, "CoolAuthor")
        self.assertEqual(bp.title, "My Inner Title")
        self.assertEqual(bp.description, "A description of the build.")
        self.assertEqual(bp.extra["extra_blueprint_urls"], [
            "https://cdn.factoriobin.com/perma/bp/a/b/abcde-xyz/fbin-abcde-1.txt"
        ])
        cache = _c.lookup_cache("factoriobin", "abcde")
        self.assertTrue(cache.cached)
        decoded = blueprint_codec.decode(cache.bp_path.read_text().strip())
        self.assertIn("blueprint", decoded)


# ---------------------------------------------------------------------------
# Live smoke tests (gated)
# ---------------------------------------------------------------------------


@unittest.skipUnless(LIVE, "set FACTORIO_SCRAPER_LIVE=1 to enable live tests")
class TestLiveSmoke(unittest.TestCase):
    """Real network. One blueprint per shipped site.

    These exist so we notice when a backend changes shape. They also
    populate the local cache; after running these the user has at
    least one real blueprint per site to look at.
    """

    def setUp(self) -> None:
        # Reset only the rate limiter; keep the real library/external/ cache.
        _c.RateLimiter._default = _c.RateLimiter()

    def _assert_round_trip(self, site_module, ref_id: str) -> None:
        bp = site_module.fetch_one(ref_id)
        self.assertTrue(bp.author, f"{site_module.SITE} blueprint missing author")
        self.assertTrue(bp.url.startswith("http"), f"bad url: {bp.url}")
        self.assertTrue(bp.fetched_at.endswith("Z"), f"bad fetched_at: {bp.fetched_at}")
        cache = _c.lookup_cache(site_module.SITE, ref_id)
        self.assertTrue(cache.has_bp, "no cached .bp file")
        self.assertTrue(cache.has_json, "no cached .json file")
        self.assertGreater(cache.bp_path.stat().st_size, 0)
        decoded = blueprint_codec.decode(cache.bp_path.read_text().strip())
        # Either a single blueprint or a book is acceptable.
        self.assertTrue("blueprint" in decoded or "blueprint_book" in decoded,
                        f"decoded payload has no blueprint envelope: {list(decoded)}")

    def test_factorio_school_live(self) -> None:
        refs = _fs.discover(query="recent", limit=1)
        self.assertTrue(refs, "no refs returned from factorio.school")
        self._assert_round_trip(_fs, refs[0].id)

    def test_factorioprints_live(self) -> None:
        refs = _fp.discover(query="recent", limit=1)
        self.assertTrue(refs)
        self._assert_round_trip(_fp, refs[0].id)

    def test_factoriobin_live(self) -> None:
        # The demo post is the only stable, public id.
        self._assert_round_trip(_fb, _fb.DEMO_ID)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main(verbosity=2)
