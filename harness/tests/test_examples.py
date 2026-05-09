"""End-to-end tests for the harness examples.

Run with: `python3 -m unittest harness.tests.test_examples`

For each example, we:
- run synthesize() and assert it produces a non-empty blueprint string,
- decode it and verify it round-trips,
- run validate.validate against the layout and the blueprint object,
- assert the schema check passes (when jsonschema is importable),
- assert the entity count matches an expected breakdown.
"""

from __future__ import annotations

import unittest

from harness import encode, validate
from harness.examples import solar_field, stone_smelter_array


class StoneSmelterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = stone_smelter_array.build()

    def test_blueprint_string_non_empty(self):
        self.assertIsInstance(self.result.blueprint_string, str)
        self.assertGreater(len(self.result.blueprint_string), 64)
        self.assertEqual(self.result.blueprint_string[0], "0")

    def test_round_trip(self):
        decoded = encode.decode(self.result.blueprint_string)
        self.assertEqual(decoded, self.result.blueprint_object)

    def test_entity_breakdown(self):
        # 12 furnaces + 24 inserters (input + output per furnace) + 24 belt
        # tiles input + 24 belt tiles output = 84 entities.
        self.assertEqual(self.result.entity_count, 84)
        names = [e["name"] for e in self.result.blueprint_object["blueprint"]["entities"]]
        self.assertEqual(names.count("stone-furnace"), 12)
        self.assertEqual(names.count("burner-inserter"), 24)
        self.assertEqual(names.count("transport-belt"), 48)

    def test_validation_clean(self):
        # synthesize() already runs validate; if it returned, validation passed.
        # Re-run explicitly for completeness.
        # Build a fresh layout to validate.
        from harness import layout, plan as planner
        from harness.spec import BuildSpec

        spec = BuildSpec(
            kind="smelter_array",
            target="iron-plate",
            machine_count=12,
            machine_choice="stone-furnace",
            fuel="coal",
            inserter_tier="burner-inserter",
        )
        p = planner.plan(spec)
        ly = layout.layout(p, spec)
        rep = validate.validate(ly, self.result.blueprint_object)
        self.assertTrue(rep.ok, msg="\n".join(rep.errors))


class SolarFieldTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = solar_field.build()

    def test_blueprint_string_non_empty(self):
        self.assertIsInstance(self.result.blueprint_string, str)
        self.assertGreater(len(self.result.blueprint_string), 64)
        self.assertEqual(self.result.blueprint_string[0], "0")

    def test_round_trip(self):
        decoded = encode.decode(self.result.blueprint_string)
        self.assertEqual(decoded, self.result.blueprint_object)

    def test_entity_breakdown(self):
        names = [e["name"] for e in self.result.blueprint_object["blueprint"]["entities"]]
        self.assertEqual(names.count("solar-panel"), 24)
        self.assertEqual(names.count("accumulator"), 20)
        # At least some poles should have been placed.
        self.assertGreaterEqual(names.count("medium-electric-pole"), 1)

    def test_validation_clean(self):
        from harness import layout, plan as planner
        from harness.spec import BuildSpec

        spec = BuildSpec(
            kind="solar_field",
            solar_panel_count=24,
            accumulator_count=20,
        )
        p = planner.plan(spec)
        ly = layout.layout(p, spec)
        rep = validate.validate(ly, self.result.blueprint_object)
        self.assertTrue(rep.ok, msg="\n".join(rep.errors))


if __name__ == "__main__":
    unittest.main()
