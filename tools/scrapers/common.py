"""Shared scraper plumbing: HTTP, robots.txt, rate limit, cache, metadata.

All scraper modules should funnel HTTP through `RateLimiter.fetch()` so that
robots.txt, the global request budget, and per-host courtesy delays are all
enforced in one place.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

USER_AGENT = (
    "factorio-blueprints-toolkit/0.1 "
    "(+https://github.com/gabrielsecco22/factorio_blueprints)"
)
DEFAULT_TIMEOUT = 30.0
MIN_DELAY_BETWEEN_REQUESTS_S = 2.0
MAX_REQUESTS_PER_SESSION = 100


# ---------------------------------------------------------------------------
# Library / cache layout
# ---------------------------------------------------------------------------


def library_root() -> Path:
    """Return the absolute path to `library/external/` in the repo."""
    here = Path(__file__).resolve()
    # tools/scrapers/common.py -> repo/tools/scrapers/common.py
    repo_root = here.parents[2]
    out = repo_root / "library" / "external"
    out.mkdir(parents=True, exist_ok=True)
    return out


def cache_path_for(site: str, blueprint_id: str, suffix: str) -> Path:
    """Return the cache path for a given site + blueprint id + suffix."""
    if not site or "/" in site or ".." in site:
        raise ValueError(f"invalid site name: {site!r}")
    if not blueprint_id:
        raise ValueError("blueprint_id required")
    safe_id = _safe_filename(blueprint_id)
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    site_dir = library_root() / site
    site_dir.mkdir(parents=True, exist_ok=True)
    return site_dir / f"{safe_id}{suffix}"


def _safe_filename(s: str) -> str:
    """Make a string safe to use as a file name on Linux/macOS/Windows.

    Keeps alnum, dash, underscore, dot. Replaces everything else with '_'.
    Limits length to 120 chars.
    """
    if not s:
        return "_"
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        else:
            out.append("_")
    cleaned = "".join(out).strip("._") or "_"
    return cleaned[:120]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BlueprintRef:
    """Lightweight reference returned by `discover()`. No blueprint string."""

    site: str
    id: str
    title: str
    author: str
    url: str
    tags: list[str] = field(default_factory=list)
    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Blueprint:
    """Full result returned by `fetch_one()`. The blueprint string is required."""

    site: str
    id: str
    title: str
    author: str
    url: str
    blueprint_string: str
    tags: list[str] = field(default_factory=list)
    description: str = ""
    fetched_at: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("blueprint_string")
        return d


@dataclass
class CacheEntry:
    """Result of a cache lookup."""

    bp_path: Path
    json_path: Path
    has_bp: bool
    has_json: bool

    @property
    def cached(self) -> bool:
        return self.has_bp and self.has_json


def lookup_cache(site: str, blueprint_id: str) -> CacheEntry:
    bp = cache_path_for(site, blueprint_id, "bp")
    js = cache_path_for(site, blueprint_id, "json")
    return CacheEntry(
        bp_path=bp,
        json_path=js,
        has_bp=bp.is_file() and bp.stat().st_size > 0,
        has_json=js.is_file() and js.stat().st_size > 0,
    )


def save_blueprint(bp: Blueprint) -> CacheEntry:
    """Write `<id>.bp` (raw string) and `<id>.json` (metadata)."""
    entry = lookup_cache(bp.site, bp.id)
    entry.bp_path.write_text(bp.blueprint_string.strip() + "\n", encoding="utf-8")
    entry.json_path.write_text(
        json.dumps(bp.to_metadata(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    entry.has_bp = True
    entry.has_json = True
    return entry


def write_metadata(site: str, blueprint_id: str, meta: dict[str, Any]) -> Path:
    p = cache_path_for(site, blueprint_id, "json")
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


class _Robots:
    """RFC 9309-style robots.txt matcher.

    Why not stdlib `urllib.robotparser`? It does not understand the
    `*` wildcard or `$` end-of-URL anchor that Google standardized
    (and that real sites rely on, e.g. Firebase's
    `Allow: /*.json$`). We parse just the bits we need: per-UA groups,
    Allow / Disallow with longest-match wins, and `*`/`$` patterns.
    """

    def __init__(self) -> None:
        # Each element is (uas: list[str], rules: list[(allow: bool, pattern: str)])
        self._groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
        self._raw_text: str = ""

    def parse(self, text: str) -> None:
        self._raw_text = text
        cur_uas: list[str] = []
        cur_rules: list[tuple[bool, str]] = []
        last_was_ua = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, _, value = line.partition(":")
            field = field.strip().lower()
            value = value.strip()
            if field == "user-agent":
                if cur_rules and cur_uas and not last_was_ua:
                    self._groups.append((cur_uas, cur_rules))
                    cur_uas = []
                    cur_rules = []
                cur_uas.append(value.lower())
                last_was_ua = True
            elif field in ("allow", "disallow"):
                last_was_ua = False
                if not cur_uas:
                    # rule before any user-agent: treat as global
                    cur_uas = ["*"]
                cur_rules.append((field == "allow", value))
        if cur_uas:
            self._groups.append((cur_uas, cur_rules))

    @staticmethod
    def _ua_matches(token: str, ua_string: str) -> bool:
        if token == "*":
            return True
        # robots tokens are case-insensitive substrings of the UA product.
        return token.lower() in ua_string.lower()

    def _rules_for(self, ua_string: str) -> list[tuple[bool, str]]:
        # Per RFC: pick the most specific group whose name is a substring
        # of the user-agent product token. Fall back to '*' group.
        best: list[tuple[bool, str]] | None = None
        best_len = -1
        star_rules: list[tuple[bool, str]] | None = None
        for uas, rules in self._groups:
            if "*" in uas:
                star_rules = (star_rules or []) + rules
            for token in uas:
                if token == "*":
                    continue
                if self._ua_matches(token, ua_string) and len(token) > best_len:
                    best = rules
                    best_len = len(token)
        return best if best is not None else (star_rules or [])

    @staticmethod
    def _compile(pattern: str) -> re.Pattern[str]:
        # Anchor at start. `*` -> `.*`. `$` at end -> end-of-line anchor.
        end_anchor = pattern.endswith("$")
        body = pattern[:-1] if end_anchor else pattern
        regex = "^"
        for ch in body:
            if ch == "*":
                regex += ".*"
            else:
                regex += re.escape(ch)
        if end_anchor:
            regex += "$"
        return re.compile(regex)

    def can_fetch(self, ua_string: str, url: str) -> tuple[bool, str]:
        """Return (allowed, rule_explanation)."""
        path = urllib.parse.urlsplit(url).path or "/"
        query = urllib.parse.urlsplit(url).query
        path_with_q = path + ("?" + query if query else "")

        rules = self._rules_for(ua_string)
        if not rules:
            return True, "no applicable rules"

        # Per RFC 9309 / Google: longest match wins; on equal length, allow wins.
        best_rule: tuple[bool, str] | None = None
        best_len = -1
        for allow, pattern in rules:
            if pattern == "":
                # empty Disallow == allow all. empty Allow == nothing.
                if not allow:
                    if 0 > best_len:
                        best_rule = (True, "(empty Disallow)")
                        best_len = 0
                continue
            try:
                pat = self._compile(pattern)
            except re.error:
                continue
            if pat.match(path_with_q):
                length = len(pattern)
                if length > best_len or (length == best_len and allow and (
                    best_rule is None or not best_rule[0]
                )):
                    best_rule = (allow, f"{'Allow' if allow else 'Disallow'}: {pattern}")
                    best_len = length

        if best_rule is None:
            return True, "no matching rule"
        return best_rule[0], best_rule[1]


class RobotsCache:
    """Per-host robots.txt cache.

    Uses our internal `_Robots` matcher because the stdlib parser
    rejects the `*`/`$` syntax that real sites (Firebase, GitHub
    Pages, etc.) depend on.
    """

    def __init__(self, user_agent: str = USER_AGENT) -> None:
        self.user_agent = user_agent
        self._parsers: dict[str, _Robots] = {}
        self.last_decision: tuple[str, bool, str] | None = None

    def _origin(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme or not parts.netloc:
            raise ValueError(f"cannot derive origin from url: {url!r}")
        return f"{parts.scheme}://{parts.netloc}"

    def _parser_for(self, url: str) -> _Robots:
        origin = self._origin(url)
        if origin in self._parsers:
            return self._parsers[origin]
        rp = _Robots()
        robots_url = origin + "/robots.txt"
        try:
            req = urllib.request.Request(robots_url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            rp.parse(content)
        except (urllib.error.URLError, TimeoutError, OSError):
            # If robots.txt is unreachable, the conservative interpretation
            # is to allow (matches Google's behavior). Sites with strict
            # policies publish a robots.txt; an outright fetch failure is rare.
            rp.parse("User-agent: *\nAllow: /\n")
        self._parsers[origin] = rp
        return rp

    def can_fetch(self, url: str) -> bool:
        rp = self._parser_for(url)
        allowed, rule = rp.can_fetch(self.user_agent, url)
        self.last_decision = (url, allowed, rule)
        return allowed


# ---------------------------------------------------------------------------
# Rate limiter / fetcher
# ---------------------------------------------------------------------------


class RateLimitExceeded(RuntimeError):
    """Raised when MAX_REQUESTS_PER_SESSION is reached."""


class RobotsDisallowed(RuntimeError):
    """Raised when robots.txt forbids the URL."""


class RateLimiter:
    """One per process. Singleton helper provided via `get_default()`."""

    _default: "RateLimiter | None" = None

    def __init__(
        self,
        *,
        min_delay_s: float = MIN_DELAY_BETWEEN_REQUESTS_S,
        max_requests: int = MAX_REQUESTS_PER_SESSION,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.min_delay_s = min_delay_s
        self.max_requests = max_requests
        self.user_agent = user_agent
        self.requests_made = 0
        self._last_request_at_per_host: dict[str, float] = {}
        self.robots = RobotsCache(user_agent=user_agent)

    @classmethod
    def get_default(cls) -> "RateLimiter":
        if cls._default is None:
            cls._default = cls()
        return cls._default

    def _wait_for_host(self, host: str) -> None:
        last = self._last_request_at_per_host.get(host)
        if last is None:
            return
        elapsed = time.monotonic() - last
        delay = self.min_delay_s - elapsed
        if delay > 0:
            time.sleep(delay)

    def _stamp_host(self, host: str) -> None:
        self._last_request_at_per_host[host] = time.monotonic()

    def fetch(
        self,
        url: str,
        *,
        accept: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> tuple[bytes, str, dict[str, str]]:
        """Fetch a URL. Returns (body, content_type, headers).

        Enforces robots.txt, courtesy delay, request budget, Retry-After.
        """
        if self.requests_made >= self.max_requests:
            raise RateLimitExceeded(
                f"hit session cap of {self.max_requests} requests; aborting"
            )
        if not self.robots.can_fetch(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

        host = urllib.parse.urlsplit(url).netloc
        self._wait_for_host(host)

        headers = {"User-Agent": self.user_agent}
        if accept:
            headers["Accept"] = accept
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(url, headers=headers)
        # Honor Retry-After on 429/503 with up to 3 retries, then bail.
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read()
                    content_type = resp.headers.get_content_type()
                    resp_headers = {k: v for k, v in resp.headers.items()}
                self.requests_made += 1
                self._stamp_host(host)
                return body, content_type, resp_headers
            except urllib.error.HTTPError as exc:
                self.requests_made += 1
                self._stamp_host(host)
                if exc.code in (429, 503) and attempt < 3:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    delay = _parse_retry_after(retry_after) or (self.min_delay_s * (2 ** attempt))
                    time.sleep(delay)
                    attempt += 1
                    continue
                raise

    def fetch_text(
        self,
        url: str,
        *,
        accept: str | None = None,
        encoding: str = "utf-8",
        extra_headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        body, _ct, _hdrs = self.fetch(
            url, accept=accept, extra_headers=extra_headers, timeout=timeout
        )
        return body.decode(encoding, errors="replace")

    def fetch_json(
        self,
        url: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Any:
        text = self.fetch_text(
            url,
            accept="application/json",
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return json.loads(text)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    # delta-seconds form
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    # HTTP-date form
    try:
        dt = _dt.datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT")
        dt = dt.replace(tzinfo=_dt.timezone.utc)
        return max(0.0, (dt - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Manifest writer
# ---------------------------------------------------------------------------


def update_manifest(site: str, refs: Iterable[BlueprintRef]) -> Path:
    """Append/refresh the per-site manifest of every cached id we know about."""
    manifest_path = library_root() / site / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, Any]] = {}
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    for ref in refs:
        existing[ref.id] = ref.to_dict()
    manifest_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def status_for_site(site: str) -> dict[str, Any]:
    """Return a small dict summarizing how much we have cached for `site`."""
    site_dir = library_root() / site
    if not site_dir.is_dir():
        return {"site": site, "cached_blueprints": 0, "bytes": 0}
    bp_files = sorted(site_dir.glob("*.bp"))
    json_files = {p.stem for p in site_dir.glob("*.json") if p.stem != "manifest"}
    total = sum(p.stat().st_size for p in site_dir.iterdir() if p.is_file())
    return {
        "site": site,
        "path": str(site_dir),
        "cached_blueprints": len(bp_files),
        "metadata_files": len(json_files),
        "bytes": total,
        "ids_sample": [p.stem for p in bp_files[:5]],
    }


# Re-export for convenience.
__all__ = [
    "Blueprint",
    "BlueprintRef",
    "CacheEntry",
    "DEFAULT_TIMEOUT",
    "MAX_REQUESTS_PER_SESSION",
    "MIN_DELAY_BETWEEN_REQUESTS_S",
    "RateLimiter",
    "RateLimitExceeded",
    "RobotsCache",
    "RobotsDisallowed",
    "USER_AGENT",
    "cache_path_for",
    "library_root",
    "lookup_cache",
    "save_blueprint",
    "status_for_site",
    "update_manifest",
    "utc_now_iso",
    "write_metadata",
]


# Allow this file to be imported even when invoked as a script.
if "PYTHONPATH" in os.environ:
    pass
