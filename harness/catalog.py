"""Lazy loaders for `specs/*.json`.

All loaders return dicts keyed by prototype name. Some source JSONs are
stored as lists; those are reshaped into name-keyed dicts here. Results
are cached for the lifetime of the process. The directory is resolved
relative to the repo root regardless of cwd, so the harness can be
invoked from anywhere.
"""

from __future__ import annotations

import json
import pathlib
from functools import lru_cache
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS = REPO_ROOT / "specs"


def _load_json(name: str) -> Any:
    return json.loads((SPECS / name).read_text())


def _by_name(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {it["name"]: it for it in items}


@lru_cache(maxsize=None)
def recipes() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("recipes.json"))


@lru_cache(maxsize=None)
def machines() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("machines.json"))


@lru_cache(maxsize=None)
def items() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("items.json"))


@lru_cache(maxsize=None)
def fluids() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("fluids.json"))


@lru_cache(maxsize=None)
def belts() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("belts.json"))


@lru_cache(maxsize=None)
def inserters() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("inserters.json"))


@lru_cache(maxsize=None)
def modules() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("modules.json"))


@lru_cache(maxsize=None)
def beacons() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("beacons.json"))


@lru_cache(maxsize=None)
def quality() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("quality.json"))


@lru_cache(maxsize=None)
def planets() -> dict[str, dict[str, Any]]:
    return _by_name(_load_json("planets.json"))


@lru_cache(maxsize=None)
def recipe_categories() -> dict[str, Any]:
    return _load_json("recipe_categories.json")


@lru_cache(maxsize=None)
def electric_network() -> dict[str, Any]:
    """Returns the raw electric_network.json dict (poles, accumulators, ...)."""
    return _load_json("electric_network.json")


@lru_cache(maxsize=None)
def poles() -> dict[str, dict[str, Any]]:
    return _by_name(electric_network()["poles"])


@lru_cache(maxsize=None)
def solar_panels() -> dict[str, dict[str, Any]]:
    return _by_name(electric_network()["solar_panels"])


@lru_cache(maxsize=None)
def accumulators() -> dict[str, dict[str, Any]]:
    return _by_name(electric_network()["accumulators"])


@lru_cache(maxsize=None)
def blueprint_schema() -> dict[str, Any]:
    return _load_json("blueprint_schema.json")


# ---------------------------------------------------------------------------
# Footprint table.
#
# `specs/machines.json` carries `tile_size` for crafting machines but not for
# poles / belts / inserters / solar / accumulators (those live in
# `data-raw-dump.json` only). We hard-code the verified footprints here so
# the harness has a single source of truth without reloading 28 MB of dump
# data on every run. All values were cross-checked against
# `data-raw-dump.json` (see commit message for verification).
# ---------------------------------------------------------------------------

# (tile_w, tile_h). Square footprints only for now.
_FOOTPRINTS: dict[str, tuple[int, int]] = {
    # Poles
    "small-electric-pole": (1, 1),
    "medium-electric-pole": (1, 1),
    "big-electric-pole": (2, 2),
    "substation": (2, 2),
    # Solar / power
    "solar-panel": (3, 3),
    "accumulator": (2, 2),
    # Beacons
    "beacon": (3, 3),
    # Belts
    "transport-belt": (1, 1),
    "fast-transport-belt": (1, 1),
    "express-transport-belt": (1, 1),
    "turbo-transport-belt": (1, 1),
    # Inserters
    "inserter": (1, 1),
    "fast-inserter": (1, 1),
    "long-handed-inserter": (1, 1),
    "burner-inserter": (1, 1),
    "bulk-inserter": (1, 1),
    "stack-inserter": (1, 1),
}


def footprint(name: str) -> tuple[int, int]:
    """Return (tile_w, tile_h) for the named entity.

    Looks up `tile_size` on machines first, then the static footprint
    table. Raises KeyError if unknown.
    """
    m = machines().get(name)
    if m and m.get("tile_size"):
        ts = m["tile_size"]
        return (int(ts[0]), int(ts[1]))
    if name in _FOOTPRINTS:
        return _FOOTPRINTS[name]
    raise KeyError(f"footprint unknown for entity {name!r}; add to harness/catalog._FOOTPRINTS")
