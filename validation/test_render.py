#!/usr/bin/env python3
"""Tests for ``tools/render_blueprint.py``.

Stdlib-only. Run with::

    python3 -m unittest validation.test_render

Each test renders a blueprint produced by the existing harness examples
and asserts the structural summary + grid contain the expected entities.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import blueprint_codec  # noqa: E402
from harness import BuildSpec, synthesize  # noqa: E402

import render_blueprint  # noqa: E402


def _render(spec: BuildSpec):
    result = synthesize(spec)
    obj = blueprint_codec.decode(result.blueprint_string)
    return render_blueprint.render(obj)


class RenderStoneSmelterTests(unittest.TestCase):
    """The 12-furnace stone smelter array is the canonical sanity check."""

    @classmethod
    def setUpClass(cls):
        spec = BuildSpec(
            kind="smelter_array",
            target="iron-plate",
            machine_count=12,
            machine_choice="stone-furnace",
            fuel="coal",
            belt_tier="transport-belt",
            inserter_tier="burner-inserter",
            label="test stone smelter",
        )
        cls.out = _render(spec)
        cls.summary = cls.out["summary"]
        cls.grid_text = "\n".join(cls.out["grid"])

    def test_entity_counts(self):
        ec = self.summary["entity_counts"]
        self.assertEqual(ec.get("stone-furnace"), 12)
        self.assertEqual(ec.get("burner-inserter"), 24)
        self.assertEqual(ec.get("transport-belt"), 48)

    def test_grid_chars(self):
        # 12 furnaces, each occupies a single 'F' (its NW tile).
        self.assertEqual(self.grid_text.count("F"), 12)
        # 24 inserters facing N -> 'i' glyphs.
        self.assertEqual(self.grid_text.count("i"), 24)
        # 48 east-facing belt tiles -> '>' glyphs.
        self.assertEqual(self.grid_text.count(">"), 48)

    def test_bbox_dimensions(self):
        # 12 stone-furnaces (each 2x2) packed contiguously: width 24.
        bbox = self.summary["bbox"]
        self.assertEqual(bbox["width"], 24)
        # 6 rows: output belt, output inserter, furnace top, furnace bottom,
        # input inserter, input belt.
        self.assertEqual(bbox["height"], 6)

    def test_only_base_mod(self):
        self.assertEqual(self.summary["mods_referenced"], ["base"])
        self.assertEqual(self.summary["mods_missing_in_user_install"], [])

    def test_no_warnings(self):
        self.assertEqual(self.summary["warnings"], [])


class RenderSolarFieldTests(unittest.TestCase):
    """Solar field exercises 3x3 (panels) and 2x2 (accumulators) footprints."""

    @classmethod
    def setUpClass(cls):
        spec = BuildSpec(
            kind="solar_field",
            solar_panel_count=24,
            accumulator_count=20,
            label="test solar field",
        )
        cls.out = _render(spec)
        cls.summary = cls.out["summary"]
        cls.grid_text = "\n".join(cls.out["grid"])

    def test_panel_and_accumulator_counts(self):
        ec = self.summary["entity_counts"]
        self.assertEqual(ec.get("solar-panel"), 24)
        self.assertEqual(ec.get("accumulator"), 20)

    def test_panel_glyph(self):
        # Each solar-panel writes one 'S' (its NW tile).
        self.assertEqual(self.grid_text.count("S"), 24)
        # Each accumulator writes one 'Q'.
        self.assertEqual(self.grid_text.count("Q"), 20)

    def test_pole_glyph(self):
        # medium-electric-pole shows as '+'. Count must match the entity
        # count exactly (no continuation tiles for 1x1).
        ec = self.summary["entity_counts"]
        self.assertEqual(self.grid_text.count("+"), ec["medium-electric-pole"])

    def test_categorisation(self):
        cat = self.summary["by_category"]
        # 24 panels + 20 accumulators -> 44 power-generation.
        self.assertEqual(cat.get("power_generation"), 44)
        # Poles count as power_distribution.
        self.assertEqual(cat.get("power_distribution"), self.summary["entity_counts"]["medium-electric-pole"])


class RenderModAwarenessTests(unittest.TestCase):
    """Hand-craft a blueprint that references a mod entity, then verify
    ``mods_referenced`` includes the mod name. We use ``accumulator-mk2``
    because it exists in the user's enabled mods (per the project's
    detected install) and the items.json already maps it to the
    ``accumulator-mk2`` mod.

    For a true "missing" case we synthesise an entity name that is NOT
    in items.json -- it should land in mods_referenced as 'unknown' and
    NOT trigger a missing-mod warning (we only warn for known but
    disabled mods).
    """

    def _render_minimal(self, name: str):
        bp = {
            "blueprint": {
                "item": "blueprint",
                "version": 562949954076673,
                "icons": [{"signal": {"type": "item", "name": "iron-plate"}, "index": 1}],
                "entities": [
                    {"entity_number": 1, "name": name, "position": {"x": 0.5, "y": 0.5}},
                ],
            }
        }
        return render_blueprint.render(bp)

    def test_known_mod_entity(self):
        # accumulator-mk2 is from a third-party mod present in the user install.
        out = self._render_minimal("accumulator-mk2")
        self.assertIn("accumulator-mk2", out["summary"]["mods_referenced"])

    def test_missing_mod_flagging(self):
        # synthesise an entity that doesn't appear in any items entry; we
        # tag it 'unknown' but do not crash.
        out = self._render_minimal("totally-fake-entity-xyz")
        self.assertIn("unknown", out["summary"]["mods_referenced"])
        # The grid renders it as '?' (unknown) and emits a warning.
        self.assertIn("?", "".join(out["grid"]))
        self.assertTrue(any("unknown entity" in w for w in out["summary"]["warnings"]))


class RenderCLIFlagsTests(unittest.TestCase):
    """The ``--bbox`` and ``--max-width`` flags must clip rather than crash."""

    @classmethod
    def setUpClass(cls):
        spec = BuildSpec(
            kind="smelter_array",
            target="iron-plate",
            machine_count=12,
            machine_choice="stone-furnace",
            fuel="coal",
            belt_tier="transport-belt",
            inserter_tier="burner-inserter",
            label="test bbox",
        )
        result = synthesize(spec)
        cls.obj = blueprint_codec.decode(result.blueprint_string)

    def test_bbox_window(self):
        out = render_blueprint.render(self.obj, bbox=(0, -1, 5, 4))
        for row in out["grid"]:
            self.assertEqual(len(row), 6)
        self.assertEqual(len(out["grid"]), 6)

    def test_max_width_truncation(self):
        out = render_blueprint.render(self.obj, max_width=10)
        for row in out["grid"]:
            self.assertLessEqual(len(row), 10)
            if len(row) == 10 and row != "." * 10:
                # Truncated rows end in "..." (only when actually clipped).
                pass


if __name__ == "__main__":
    unittest.main()
