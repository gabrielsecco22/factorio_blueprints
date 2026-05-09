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
from harness.examples import (
    electric_smelter_array,
    green_circuit_block,
    solar_field,
    steel_smelter_array,
    stone_smelter_array,
)


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


class SteelSmelterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = steel_smelter_array.build()

    def test_blueprint_string_non_empty(self):
        self.assertIsInstance(self.result.blueprint_string, str)
        self.assertGreater(len(self.result.blueprint_string), 64)
        self.assertEqual(self.result.blueprint_string[0], "0")

    def test_round_trip(self):
        decoded = encode.decode(self.result.blueprint_string)
        self.assertEqual(decoded, self.result.blueprint_object)

    def test_entity_breakdown(self):
        # 24 furnaces + (24 output + 24 ore + 24 fuel) inserters + 96 belts.
        self.assertEqual(self.result.entity_count, 24 + 72 + 96)
        names = [e["name"] for e in self.result.blueprint_object["blueprint"]["entities"]]
        self.assertEqual(names.count("steel-furnace"), 24)
        self.assertEqual(names.count("burner-inserter"), 72)
        self.assertEqual(names.count("transport-belt"), 96)
        # The fuel-feed inserter should carry a coal filter on each furnace.
        fuel_filtered = [
            e for e in self.result.blueprint_object["blueprint"]["entities"]
            if e["name"] == "burner-inserter" and e.get("filters")
        ]
        self.assertEqual(len(fuel_filtered), 24)
        for ent in fuel_filtered:
            self.assertEqual(ent["filters"][0]["name"], "coal")

    def test_validation_clean(self):
        from harness import layout, plan as planner
        from harness.spec import BuildSpec

        spec = BuildSpec(
            kind="smelter_array",
            target="iron-plate",
            machine_count=24,
            machine_choice="steel-furnace",
            fuel="coal",
            inserter_tier="burner-inserter",
            fuel_feed="shared",
        )
        p = planner.plan(spec)
        ly = layout.layout(p, spec)
        rep = validate.validate(ly, self.result.blueprint_object)
        self.assertTrue(rep.ok, msg="\n".join(rep.errors))


class ElectricSmelterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = electric_smelter_array.build()

    def test_blueprint_string_non_empty(self):
        self.assertIsInstance(self.result.blueprint_string, str)
        self.assertGreater(len(self.result.blueprint_string), 64)
        self.assertEqual(self.result.blueprint_string[0], "0")

    def test_round_trip(self):
        decoded = encode.decode(self.result.blueprint_string)
        self.assertEqual(decoded, self.result.blueprint_object)

    def test_entity_breakdown(self):
        names = [e["name"] for e in self.result.blueprint_object["blueprint"]["entities"]]
        # 24 electric furnaces, 48 plain inserters (out + in), belts span
        # 72 tiles each row -> 144 belts, plus substations covering the array.
        self.assertEqual(names.count("electric-furnace"), 24)
        self.assertEqual(names.count("inserter"), 48)
        self.assertEqual(names.count("transport-belt"), 144)
        self.assertGreaterEqual(names.count("substation"), 4)

    def test_validation_clean(self):
        from harness import layout, plan as planner
        from harness.spec import BuildSpec

        spec = BuildSpec(
            kind="electric_smelter_array",
            target="copper-plate",
            machine_count=24,
            machine_choice="electric-furnace",
            inserter_tier="inserter",
            pole_choice="substation",
        )
        p = planner.plan(spec)
        ly = layout.layout(p, spec)
        rep = validate.validate(ly, self.result.blueprint_object)
        self.assertTrue(rep.ok, msg="\n".join(rep.errors))


class GreenCircuitBlockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.result = green_circuit_block.build()

    def test_blueprint_string_non_empty(self):
        self.assertIsInstance(self.result.blueprint_string, str)
        self.assertGreater(len(self.result.blueprint_string), 64)
        self.assertEqual(self.result.blueprint_string[0], "0")

    def test_round_trip(self):
        decoded = encode.decode(self.result.blueprint_string)
        self.assertEqual(decoded, self.result.blueprint_object)

    def test_entity_breakdown(self):
        names = [e["name"] for e in self.result.blueprint_object["blueprint"]["entities"]]
        self.assertEqual(names.count("assembling-machine-1"), 10)  # 4 cable + 6 circuit
        self.assertEqual(names.count("long-handed-inserter"), 6)   # iron feed per circuit
        self.assertEqual(names.count("inserter"), 10)              # 6 circuit out + 4 copper feed
        self.assertEqual(names.count("fast-inserter"), 10)         # 6 cable->circuit + 4 cable out
        self.assertEqual(names.count("substation"), 4)
        # 4 belts each spanning 18 tiles (max(4,6)*3 = 18).
        self.assertEqual(names.count("transport-belt"), 4 * 18)
        # Each assembler must carry an explicit recipe.
        for ent in self.result.blueprint_object["blueprint"]["entities"]:
            if ent["name"] == "assembling-machine-1":
                self.assertIn(ent.get("recipe"), {"copper-cable", "electronic-circuit"})

    def test_validation_clean(self):
        from harness import layout, plan as planner
        from harness.spec import BuildSpec

        spec = BuildSpec(
            kind="green_circuit_block",
            machine_choice="assembling-machine-1",
            inserter_tier="inserter",
            pole_choice="substation",
            cable_assembler_count=4,
            circuit_assembler_count=6,
        )
        p = planner.plan(spec)
        ly = layout.layout(p, spec)
        rep = validate.validate(ly, self.result.blueprint_object)
        self.assertTrue(rep.ok, msg="\n".join(rep.errors))


if __name__ == "__main__":
    unittest.main()
