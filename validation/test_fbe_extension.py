#!/usr/bin/env python3
"""Tests for ``tools/extend_fbe_for_mods.py``.

These assume the extension has already been applied (i.e.
``python3 tools/extend_fbe_for_mods.py`` has been run since the last
``setup_fbe.sh``). They check:

1. Every Space-Age entity we care about is present in the patched
   ``data.json``.
2. Sprite assets exist on disk for those entities.
3. Beacon's modded ``module_slots`` (5, not the vanilla 2) is reflected.
4. The ``__factudio_extension__`` sentinel is written.
5. The FBE JS bundle has the PNG-load patch applied.
6. A ``beacon_smelter_array`` synthesis round-trips and every entity
   name resolves in the patched ``data.json`` (no ``MOD-MISSING``).

Run with::

    python3 -m unittest validation.test_fbe_extension

Stdlib-only.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

FBE_DATA = ROOT / "studio" / "static" / "fbe" / "data" / "data.json"
FBE_DATA_DIR = ROOT / "studio" / "static" / "fbe" / "data"
FBE_ASSETS = ROOT / "studio" / "static" / "fbe" / "assets"
DUMP_PATH = ROOT / "specs" / "data-raw-dump.json"

REQUIRED_ENTITIES = [
    "foundry",
    "electromagnetic-plant",
    "biochamber",
    "recycler",
    "cryogenic-plant",
    "agricultural-tower",
    "asteroid-collector",
    "cargo-bay",
    "space-platform-hub",
    "crusher",
]


def _load_fbe() -> dict:
    if not FBE_DATA.is_file():
        raise unittest.SkipTest(
            f"FBE bundle not installed at {FBE_DATA}; "
            "run `bash studio/setup_fbe.sh` and "
            "`python3 tools/extend_fbe_for_mods.py` first.")
    return json.loads(FBE_DATA.read_text())


class TestExtensionApplied(unittest.TestCase):
    """The patched data.json contains the Space-Age + modded entries."""

    @classmethod
    def setUpClass(cls):
        cls.fbe = _load_fbe()
        cls.sentinel = cls.fbe.get("__factudio_extension__")
        if cls.sentinel is None:
            raise unittest.SkipTest(
                "data.json has no __factudio_extension__ sentinel; "
                "run `python3 tools/extend_fbe_for_mods.py` first.")

    def test_sentinel_shape(self):
        for k in ("entities_added", "items_added", "recipes_added", "sources"):
            self.assertIn(k, self.sentinel, f"sentinel missing key: {k}")
        self.assertGreater(self.sentinel["entities_added"], 0,
                           "no entities were added; extension may have run on empty dump")
        # Sources list always includes base + core. With the user's mod
        # set we expect space-age, quality, elevated-rails too.
        srcs = set(self.sentinel.get("sources") or [])
        self.assertIn("base", srcs)
        self.assertIn("space-age", srcs)
        self.assertIn("quality", srcs)

    def test_space_age_entities_present(self):
        ents = self.fbe.get("entities", {})
        for name in REQUIRED_ENTITIES:
            self.assertIn(name, ents, f"missing entity in patched data.json: {name}")

    def test_space_age_entities_have_icon_field(self):
        ents = self.fbe["entities"]
        for name in REQUIRED_ENTITIES:
            entry = ents[name]
            icon = entry.get("icon") or (
                (entry.get("icons") or [{}])[0].get("icon") if entry.get("icons") else None
            )
            self.assertIsNotNone(icon, f"{name}: no icon field")

    def test_modded_beacon_module_slots(self):
        beacon = self.fbe["entities"].get("beacon")
        self.assertIsNotNone(beacon, "beacon entity missing from data.json")
        # AdjustableModule (one of the user's enabled mods) sets beacon
        # module_slots from 2 -> 5.
        self.assertEqual(beacon.get("module_slots"), 5,
                         f"beacon.module_slots={beacon.get('module_slots')} "
                         "expected 5 (modded by AdjustableModule)")

    def test_modded_beacon_distribution_effectivity(self):
        beacon = self.fbe["entities"].get("beacon")
        # AdjustableModule (or similar) bumps distribution_effectivity
        # from 1.5 -> 3.
        self.assertEqual(beacon.get("distribution_effectivity"), 3,
                         f"beacon.distribution_effectivity={beacon.get('distribution_effectivity')} "
                         "expected 3 (modded)")

    def test_assembling_machine_3_module_slots_overlay(self):
        am3 = self.fbe["entities"].get("assembling-machine-3")
        self.assertIsNotNone(am3)
        # AdjustableModule adds +1 module slot to all crafters: 4 -> 5.
        self.assertEqual(am3.get("module_slots"), 5,
                         f"assembling-machine-3.module_slots={am3.get('module_slots')} "
                         "expected 5 (modded)")

    def test_dump_consistency_for_overlays(self):
        """Patched values must match the dump for every overlay field."""
        if not DUMP_PATH.is_file():
            self.skipTest(f"no dump at {DUMP_PATH}")
        dump = json.loads(DUMP_PATH.read_text())
        # Spot-check beacon and assembling-machine-3.
        for cat, name, fields in (
            ("beacon", "beacon", ("module_slots", "distribution_effectivity")),
            ("assembling-machine", "assembling-machine-3", ("module_slots",)),
            ("furnace", "electric-furnace", ("module_slots",)),
        ):
            d = dump.get(cat, {}).get(name)
            f = self.fbe["entities"].get(name)
            if d is None or f is None:
                continue
            for field in fields:
                self.assertEqual(f.get(field), d.get(field),
                                 f"{name}.{field}: patched={f.get(field)} "
                                 f"dump={d.get(field)}")


class TestSpritesOnDisk(unittest.TestCase):
    """Sprites should be readable PNGs on the local filesystem."""

    @classmethod
    def setUpClass(cls):
        cls.fbe = _load_fbe()

    def _entity_sprites(self, name: str) -> set[str]:
        entry = self.fbe["entities"].get(name)
        if entry is None:
            return set()
        text = json.dumps(entry, separators=(",", ":"))
        return set(re.findall(r'__[A-Za-z0-9_\-]+__/[^"\\]+\.png', text))

    def test_required_entities_have_sprites_on_disk(self):
        missing_per_entity: dict[str, list[str]] = {}
        for name in REQUIRED_ENTITIES:
            sprites = self._entity_sprites(name)
            missing = []
            for ref in sprites:
                m = re.match(r"__([A-Za-z0-9_\-]+)__/(.+)$", ref)
                if not m:
                    continue
                p = FBE_DATA_DIR / f"__{m.group(1)}__" / m.group(2)
                if not p.is_file() or p.stat().st_size == 0:
                    missing.append(ref)
            if missing:
                missing_per_entity[name] = missing
        # The icon is the most important sprite. Fail if even the icon
        # for any required entity is missing.
        for name in REQUIRED_ENTITIES:
            entry = self.fbe["entities"][name]
            icon = entry.get("icon")
            self.assertIsNotNone(icon)
            m = re.match(r"__([A-Za-z0-9_\-]+)__/(.+)$", icon)
            self.assertIsNotNone(m, f"{name}.icon not in expected schema: {icon}")
            p = FBE_DATA_DIR / f"__{m.group(1)}__" / m.group(2)
            self.assertTrue(p.is_file(),
                            f"{name}: icon sprite missing on disk: {p}")
        if missing_per_entity:
            # Non-fatal info: report missing non-icon sprites for debugging.
            sys.stderr.write(
                f"info: {len(missing_per_entity)} entities have some missing "
                "non-icon sprites (icons OK):\n")
            for n, refs in missing_per_entity.items():
                sys.stderr.write(f"  {n}: {len(refs)} missing\n")


class TestBundlePatched(unittest.TestCase):
    """The PixiJS basis-vs-png replace patch must be applied."""

    def test_bundle_loads_png_directly(self):
        if not FBE_ASSETS.is_dir():
            self.skipTest(f"no FBE assets dir at {FBE_ASSETS}")
        js_files = list(FBE_ASSETS.glob("*.js"))
        if not js_files:
            self.skipTest("no JS files in FBE assets dir")
        # The original substring must NOT be present anywhere; the
        # patched substring must be present in at least one file.
        old = '.replace(".png",".basis")'
        new = '.replace(".png",".png"  )'
        any_new = False
        for p in js_files:
            text = p.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(old, text,
                             f"{p.name}: still contains the unpatched basis swap")
            if new in text:
                any_new = True
        self.assertTrue(any_new,
                        "no JS file contains the patched .png->.png no-op; "
                        "bundle was probably never patched (old upstream layout?)")


class TestBeaconArrayResolves(unittest.TestCase):
    """Synthesise a beacon_smelter_array and confirm every entity name
    resolves in the patched data.json (i.e. no entity from the harness
    is unknown to FBE)."""

    @classmethod
    def setUpClass(cls):
        cls.fbe = _load_fbe()
        try:
            from harness import BuildSpec, synthesize  # noqa: WPS433
            import blueprint_codec  # noqa: WPS433
        except ImportError as e:
            raise unittest.SkipTest(f"harness not importable: {e}")

        spec = BuildSpec(
            kind="beacon_smelter_array",
            target="iron-plate",
            machine_count=12,
            machine_choice="electric-furnace",
            belt_tier="fast-transport-belt",
            inserter_tier="inserter",
            beacons_per_machine=8,
            beacon_module="speed-module-3",
            machine_module="productivity-module-3",
            fuel=None,
            label="FBE extension test fixture",
        )
        result = synthesize(spec)
        cls.bp_string = result.blueprint_string
        decoded = blueprint_codec.decode(result.blueprint_string)
        body = decoded.get("blueprint") or {}
        cls.entity_names = sorted({e["name"] for e in (body.get("entities") or [])})

    def test_blueprint_synthesizes(self):
        self.assertTrue(self.bp_string.startswith("0"),
                        f"unexpected blueprint string head: {self.bp_string[:8]!r}")
        self.assertGreater(len(self.entity_names), 0)

    def test_every_entity_name_resolves(self):
        ents = self.fbe.get("entities", {})
        unknown = [n for n in self.entity_names if n not in ents]
        self.assertEqual(unknown, [],
                         f"entities not resolvable in patched data.json: {unknown}")


if __name__ == "__main__":
    unittest.main()
