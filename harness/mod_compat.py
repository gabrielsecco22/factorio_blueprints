"""Mod-attribution and compatibility checks for Factorio blueprints.

Walks decoded blueprint entities, recipes, and items, and asks
`specs/*.json` "which mod did this come from?" via the `from_mod`
field. Cross-references against the user's enabled mod list
(`~/.factorio/mods/mod-list.json`) to flag missing or disabled mods
before a blueprint is generated, imported, or pasted.

Public API:

    detect_user_mods()         -> ModSet
    required_mods_for(bp)      -> set[str]
    check_compat(req, avail)   -> CompatReport
    vanilla_substitute(name)   -> str | None
    inspect_blueprint(bp_or_s) -> InspectionReport

The `ModSet` distinguishes three states for any mod:

    enabled    - in mod-list.json with enabled=true (or DLC bundled with install)
    installed  - present in mods/*.zip (or mod-list.json) but disabled
    missing    - referenced but not installed at all

DLC: `space-age`, `quality`, `elevated-rails` are bundled with the
game install at <install>/data/, NOT in the user's mods folder, so
they always count as enabled when the user owns Space Age. We use the
existing detector's `dlc` flags as the source of truth.

Stdlib only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from harness import catalog


# Bundled DLC mods. The detector reports them via `dlc.*` flags; they
# live at <install>/data/ rather than ~/.factorio/mods/.
DLC_MODS = frozenset({"space-age", "quality", "elevated-rails"})

# Always-available bedrock mods. `base` and `core` ship with every
# install; if the user has Factorio at all, both are present.
BEDROCK_MODS = frozenset({"base", "core"})

# Static substitution table for known modded -> vanilla replacements.
# Keep this conservative: only suggest a substitute when the modded
# entity has an unambiguous vanilla equivalent that occupies the same
# blueprint role (footprint + function). Do NOT suggest replacements
# for DLC entities (you can't substitute Quality).
_VANILLA_SUBSTITUTES: dict[str, str] = {
    # promethium-belts mod (bundles a 5th belt tier on top of vanilla 2.0).
    "promethium-transport-belt": "turbo-transport-belt",
    "promethium-underground-belt": "turbo-underground-belt",
    "promethium-splitter": "turbo-splitter",
    "promethium-loader": "turbo-loader",  # vanilla 2.0 has no loader; downgrade to belt at user's risk.
    # accumulator-mk2 mod.
    "accumulator-mk2": "accumulator",
    # Bottleneck / BottleneckLite are pure-visual mods; their entities
    # are signal lamps that do not affect logistics. Drop them.
    "bottleneck-stats-lamp": None,  # type: ignore[assignment]
}


# ---------------------------------------------------------------------------
# Mod state (user's install)
# ---------------------------------------------------------------------------

@dataclass
class ModSet:
    """Snapshot of the user's mod situation.

    `enabled`   - mods active right now (will be loaded by the game).
    `disabled`  - mods present in mod-list.json but enabled=false.
    `installed_zip_only` - mods present as .zip in the mods folder but not in
                  mod-list.json at all. The game would auto-add them to
                  mod-list.json (as enabled) on next launch.
    `dlc`       - subset of `enabled` that's bundled with the install.
    `source`    - human-readable note (path or "vanilla fallback").
    """

    enabled: set[str] = field(default_factory=set)
    disabled: set[str] = field(default_factory=set)
    installed_zip_only: set[str] = field(default_factory=set)
    dlc: set[str] = field(default_factory=set)
    source: str = ""

    @property
    def all_known(self) -> set[str]:
        """Mods the user has in any state (enabled or disabled or zip-only)."""
        return self.enabled | self.disabled | self.installed_zip_only

    def state_of(self, mod: str) -> str:
        """One of: 'enabled', 'disabled', 'zip-only', 'missing'."""
        if mod in BEDROCK_MODS:
            return "enabled"
        if mod in self.enabled:
            return "enabled"
        if mod in self.disabled:
            return "disabled"
        if mod in self.installed_zip_only:
            return "zip-only"
        return "missing"


def _default_mods_dir() -> Optional[Path]:
    p = Path.home() / ".factorio" / "mods"
    if p.is_dir():
        return p
    # Flatpak Steam fallback.
    p2 = Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".factorio" / "mods"
    if p2.is_dir():
        return p2
    return None


_ZIP_NAME_RE = re.compile(r"^(.+?)_(\d+\.\d+\.\d+)\.zip$")


def _parse_zip_mod_names(mods_dir: Path) -> set[str]:
    out: set[str] = set()
    if not mods_dir.is_dir():
        return out
    for entry in mods_dir.iterdir():
        if not entry.name.endswith(".zip"):
            continue
        m = _ZIP_NAME_RE.match(entry.name)
        if m:
            out.add(m.group(1))
    return out


def detect_user_mods(mods_dir: Optional[Path] = None) -> ModSet:
    """Read the user's mod-list.json + scan the mods folder for .zip files.

    Arguments
    ---------
    mods_dir : Path, optional
        Override the default `~/.factorio/mods` location (handy for tests).

    Returns
    -------
    ModSet
        Best-effort. Returns an empty (vanilla) ModSet if no install is
        detected; bedrock + DLC remain implicitly available via their
        respective sets.
    """
    if mods_dir is None:
        mods_dir = _default_mods_dir()
    if mods_dir is None:
        return ModSet(source="(no factorio install detected)")

    enabled: set[str] = set()
    disabled: set[str] = set()
    list_path = mods_dir / "mod-list.json"
    listed: set[str] = set()
    if list_path.is_file():
        try:
            data = json.loads(list_path.read_text())
        except (OSError, json.JSONDecodeError):
            data = {"mods": []}
        for entry in data.get("mods", []):
            name = entry.get("name")
            if not name:
                continue
            listed.add(name)
            if entry.get("enabled"):
                enabled.add(name)
            else:
                disabled.add(name)

    zip_names = _parse_zip_mod_names(mods_dir)
    installed_zip_only = zip_names - listed

    # Apply DLC overlay: if the install owns Space Age the DLC mods are
    # always loaded, even though they aren't in the mods folder.
    dlc_enabled: set[str] = set()
    try:  # pragma: no cover - depends on user install
        from tools import detect_factorio  # type: ignore
        info = detect_factorio.detect()
        for flag, name in (
            ("space_age", "space-age"),
            ("quality", "quality"),
            ("elevated_rails", "elevated-rails"),
        ):
            if (info.get("dlc") or {}).get(flag):
                dlc_enabled.add(name)
                enabled.add(name)
    except Exception:
        # Detector failure is non-fatal: caller may still be vanilla.
        pass

    return ModSet(
        enabled=enabled,
        disabled=disabled,
        installed_zip_only=installed_zip_only,
        dlc=dlc_enabled,
        source=str(mods_dir),
    )


# ---------------------------------------------------------------------------
# Mod attribution
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _entity_to_mod_index() -> dict[str, str]:
    """Build a name -> from_mod lookup spanning every prototype category
    that can show up in a blueprint entity."""
    idx: dict[str, str] = {}
    # `place_result` on items maps item name -> entity name; some entities
    # only show up through their items. Index both keys so we can attribute
    # by either.
    for it in catalog.items().values():
        mod = it.get("from_mod")
        if not mod:
            continue
        idx.setdefault(it["name"], mod)
        pr = it.get("place_result")
        if pr:
            idx.setdefault(pr, mod)
    for cat in (catalog.machines, catalog.belts, catalog.inserters,
                catalog.modules, catalog.beacons, catalog.poles,
                catalog.solar_panels, catalog.accumulators):
        try:
            data = cat()
        except Exception:
            continue
        for name, proto in data.items():
            mod = proto.get("from_mod")
            if mod:
                idx.setdefault(name, mod)
    # Fallback: every prototype that exists in the dump but has no
    # `from_mod` tag becomes `base` (we know it loads in the user's
    # current mod set; we just don't know the precise origin).
    for name in _present_in_dump():
        idx.setdefault(name, "base")
    return idx


@lru_cache(maxsize=1)
def _recipe_to_mod_index() -> dict[str, str]:
    out: dict[str, str] = {}
    for n, p in catalog.recipes().items():
        mod = p.get("from_mod")
        if mod:
            out[n] = mod
        else:
            # Recipe exists in the user's dump but the extraction lost the
            # source-mod tag. Attribute to 'base' as a best guess: the
            # prototype is definitely loaded; we just don't know who owns
            # it. (Safer than reporting "unknown" for vanilla-looking names.)
            out[n] = "base"
    return out


@lru_cache(maxsize=1)
def _present_in_dump() -> set[str]:
    """Set of every entity / item / recipe name that appears in our specs.

    Used as a fallback: if a name is in the dump (so the user's install
    can place it) but the `from_mod` field is empty, we attribute it to
    `base` rather than declaring it unknown."""
    out: set[str] = set()
    out |= set(catalog.items().keys())
    out |= set(catalog.recipes().keys())
    for cat in (catalog.machines, catalog.belts, catalog.inserters,
                catalog.modules, catalog.beacons, catalog.poles,
                catalog.solar_panels, catalog.accumulators):
        try:
            out |= set(cat().keys())
        except Exception:
            continue
    return out


def mod_for_entity(name: str) -> Optional[str]:
    """Return the source mod for an entity name, or None if unknown."""
    return _entity_to_mod_index().get(name)


def mod_for_recipe(name: str) -> Optional[str]:
    return _recipe_to_mod_index().get(name)


def _decode_if_string(bp: Any) -> dict[str, Any]:
    if isinstance(bp, str):
        from harness import encode
        return encode.decode(bp)
    if isinstance(bp, dict):
        return bp
    raise TypeError("blueprint must be a blueprint string or decoded dict")


def _walk_entities(obj: Any) -> Iterable[dict[str, Any]]:
    """Yield every `entities` element nested anywhere in the structure.

    Handles plain blueprints (`{blueprint: {...}}`) AND blueprint books
    (`{blueprint_book: {blueprints: [...]}}`)."""
    if isinstance(obj, dict):
        if "entities" in obj and isinstance(obj["entities"], list):
            for e in obj["entities"]:
                if isinstance(e, dict):
                    yield e
        for v in obj.values():
            yield from _walk_entities(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_entities(it)


@dataclass
class EntityAttribution:
    """One referenced entity (or recipe / module) and its source mod."""
    name: str
    kind: str            # "entity" | "recipe" | "module" | "item" (filter)
    mod: Optional[str]   # None = unknown source
    count: int = 1


@dataclass
class RequirementSummary:
    by_mod: dict[str, list[EntityAttribution]] = field(default_factory=dict)
    unknown: list[EntityAttribution] = field(default_factory=list)

    @property
    def required_mods(self) -> set[str]:
        return set(self.by_mod.keys())


def _add(summary: RequirementSummary, attr: EntityAttribution) -> None:
    if attr.mod is None:
        # Merge duplicates so the unknown list stays compact.
        for existing in summary.unknown:
            if existing.name == attr.name and existing.kind == attr.kind:
                existing.count += attr.count
                return
        summary.unknown.append(attr)
        return
    bucket = summary.by_mod.setdefault(attr.mod, [])
    # Merge duplicates (same name + kind).
    for existing in bucket:
        if existing.name == attr.name and existing.kind == attr.kind:
            existing.count += attr.count
            return
    bucket.append(attr)


def attribute_blueprint(bp: Any) -> RequirementSummary:
    """Walk a (possibly book-shaped) blueprint and attribute every reference.

    References inspected:
      - entity `name`
      - assembling-machine `recipe`
      - inserter / loader `filters[*].name` (treated as item references)
      - per-entity `items` (modules) keys

    Returns the merged `RequirementSummary` (see fields).
    """
    obj = _decode_if_string(bp)
    summary = RequirementSummary()

    items = catalog.items()
    modules = catalog.modules()

    for ent in _walk_entities(obj):
        name = ent.get("name")
        if name:
            _add(summary, EntityAttribution(
                name=name, kind="entity",
                mod=mod_for_entity(name),
            ))
        recipe = ent.get("recipe")
        if recipe:
            _add(summary, EntityAttribution(
                name=recipe, kind="recipe",
                mod=mod_for_recipe(recipe),
            ))
        for f in ent.get("filters") or []:
            fn = f.get("name") if isinstance(f, dict) else None
            if fn:
                _add(summary, EntityAttribution(
                    name=fn, kind="item",
                    mod=(items.get(fn) or {}).get("from_mod"),
                ))
        # 2.0 blueprints carry `items` as a list of {id:{name:..}, items:{in_inventory:[...]}}.
        # Older formats use a dict.
        bp_items = ent.get("items")
        module_names: list[str] = []
        if isinstance(bp_items, dict):
            module_names.extend(k for k in bp_items.keys())
        elif isinstance(bp_items, list):
            for slot in bp_items:
                if isinstance(slot, dict):
                    nm = (slot.get("id") or {}).get("name")
                    if nm:
                        module_names.append(nm)
        for nm in module_names:
            mod = (modules.get(nm) or items.get(nm) or {}).get("from_mod")
            _add(summary, EntityAttribution(name=nm, kind="module", mod=mod))

    return summary


def required_mods_for(bp: Any) -> set[str]:
    """Lightweight wrapper around `attribute_blueprint`."""
    return attribute_blueprint(bp).required_mods


# ---------------------------------------------------------------------------
# Compatibility check
# ---------------------------------------------------------------------------

@dataclass
class CompatReport:
    required: set[str]
    enabled: set[str]
    disabled: set[str]
    missing: set[str]              # required and not installed at all
    zip_only: set[str]             # required, installed as .zip but not in mod-list.json
    unknown_entities: list[EntityAttribution] = field(default_factory=list)
    substitutes: dict[str, str] = field(default_factory=dict)  # entity_name -> vanilla name

    @property
    def ok(self) -> bool:
        return not (self.missing or self.disabled or self.zip_only or self.unknown_entities)


def vanilla_substitute(entity_name: str) -> Optional[str]:
    """Suggest a vanilla equivalent for a modded entity, or None."""
    if entity_name in _VANILLA_SUBSTITUTES:
        sub = _VANILLA_SUBSTITUTES[entity_name]
        return sub if sub else None
    return None


def check_compat(required: set[str], modset: ModSet,
                 *, attribution: Optional[RequirementSummary] = None,
                 mod_set_policy: str = "user-enabled") -> CompatReport:
    """Compare a required-mod set against the user's enabled mods.

    `mod_set_policy` controls what counts as "available":
      - 'vanilla'      : only `base`, `core`, and bundled DLC.
      - 'user-enabled' : everything in `modset.enabled` (DLC included).
      - 'user-any'     : enabled OR disabled OR zip-only (i.e. anything
                         the user could enable without downloading).
    """
    if mod_set_policy == "vanilla":
        available = set(BEDROCK_MODS) | modset.dlc
    elif mod_set_policy == "user-enabled":
        available = set(modset.enabled) | set(BEDROCK_MODS) | modset.dlc
    elif mod_set_policy == "user-any":
        available = (modset.enabled | modset.disabled | modset.installed_zip_only
                     | set(BEDROCK_MODS) | modset.dlc)
    else:
        raise ValueError(f"unknown mod_set_policy {mod_set_policy!r}")

    enabled = required & (set(modset.enabled) | set(BEDROCK_MODS) | modset.dlc)
    disabled = required & set(modset.disabled) - enabled
    zip_only = required & set(modset.installed_zip_only) - enabled - disabled
    missing = required - available - disabled - zip_only

    unknown: list[EntityAttribution] = []
    substitutes: dict[str, str] = {}
    if attribution is not None:
        unknown = list(attribution.unknown)
        for mod, attrs in attribution.by_mod.items():
            if mod in available:
                continue
            for a in attrs:
                if a.kind != "entity":
                    continue
                sub = vanilla_substitute(a.name)
                if sub:
                    substitutes[a.name] = sub

    return CompatReport(
        required=set(required),
        enabled=enabled,
        disabled=disabled,
        missing=missing,
        zip_only=zip_only,
        unknown_entities=unknown,
        substitutes=substitutes,
    )


# ---------------------------------------------------------------------------
# Inspect (CLI-friendly)
# ---------------------------------------------------------------------------

@dataclass
class InspectionReport:
    attribution: RequirementSummary
    compat: CompatReport
    modset: ModSet

    def render(self) -> str:
        lines: list[str] = ["Blueprint requires:"]
        seen: set[str] = set()
        # Render each required mod with its current state in the user's install.
        for mod in sorted(self.compat.required):
            seen.add(mod)
            state = self.modset.state_of(mod)
            note = {
                "enabled": "enabled in user install",
                "disabled": "INSTALLED but DISABLED -- enable to use this blueprint",
                "zip-only": "INSTALLED (zip present, not yet in mod-list.json)",
                "missing": "NOT INSTALLED -- blueprint will fail to import without this",
            }[state]
            lines.append(f"  {mod:<26} ({note})")
        if self.compat.unknown_entities:
            lines.append("")
            lines.append("Unknown entities (no source mod found in specs/items.json):")
            for u in self.compat.unknown_entities:
                lines.append(f"  {u.name:<26} ({u.kind}) -- likely from a mod not in your specs dump")
        if self.compat.substitutes:
            lines.append("")
            subs = ", ".join(f"{k} -> {v}" for k, v in sorted(self.compat.substitutes.items()))
            lines.append(f"Suggested vanilla equivalents available for: {subs}")
        if not lines or len(lines) == 1:
            lines.append("  (no detectable mod requirements)")
        lines.append("")
        lines.append(f"User install: {self.modset.source or '(unknown)'}")
        lines.append(
            f"  enabled={len(self.modset.enabled)} "
            f"disabled={len(self.modset.disabled)} "
            f"zip-only={len(self.modset.installed_zip_only)} "
            f"dlc={sorted(self.modset.dlc)}"
        )
        return "\n".join(lines)


def inspect_blueprint(bp: Any, modset: Optional[ModSet] = None) -> InspectionReport:
    """End-to-end: attribute + compat + render-ready report.

    `modset` defaults to `detect_user_mods()`.
    """
    if modset is None:
        modset = detect_user_mods()
    attr = attribute_blueprint(bp)
    compat = check_compat(
        attr.required_mods, modset,
        attribution=attr, mod_set_policy="user-any",
    )
    return InspectionReport(attribution=attr, compat=compat, modset=modset)
