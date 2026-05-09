"""Polite scrapers for popular Factorio blueprint sharing sites.

Each site module exposes:

    discover(query=None, limit=10) -> list[BlueprintRef]
    fetch_one(ref_or_id) -> Blueprint

Common rules enforced by `tools.scrapers.common`:

    * robots.txt is fetched and consulted before each request.
    * A minimum 2 s delay between requests per host.
    * Hard cap of 100 requests per process (lifetime of `RateLimiter`).
    * `Retry-After` is honored on 429/503.
    * All responses are cached under `library/external/<site>/`.

Stdlib only. No third-party deps.
"""

from .common import (
    Blueprint,
    BlueprintRef,
    CacheEntry,
    RateLimiter,
    RobotsCache,
    USER_AGENT,
    cache_path_for,
    library_root,
    save_blueprint,
    write_metadata,
)

__all__ = [
    "Blueprint",
    "BlueprintRef",
    "CacheEntry",
    "RateLimiter",
    "RobotsCache",
    "USER_AGENT",
    "cache_path_for",
    "library_root",
    "save_blueprint",
    "write_metadata",
]
