"""Tests for `harness.master_orchestrator` and `harness.mod_compat`.

Run with:
    python3 -m unittest validation.test_master_orchestrator
"""

from __future__ import annotations

import unittest
from typing import Any

from harness import encode
from harness.master_orchestrator import (
    MasterSpec,
    STATUS_PASS,
    STATUS_WARN,
    master_synthesize,
)
from harness import mod_compat


def _hand_blueprint(entities: list[dict[str, Any]]) -> str:
    obj = {
        "blueprint": {
            "item": "blueprint",
            "label": "test",
            "icons": [{"signal": {"name": "blueprint"}, "index": 1}],
            "entities": entities,
            "version": 562949958402048,
        }
    }
    return encode.encode(obj)


class MasterSynthesizeTest(unittest.TestCase):
    def test_iron_plate_vanilla_passes_in_few_iterations(self):
        """master_synthesize converges on iron-plate / 30/s in <= 3 iterations."""
        result = master_synthesize(MasterSpec(
            target="iron-plate",
            output_rate_per_sec=30,
            machine_choice="stone-furnace",
            fuel="coal",
            max_iterations=3,
            mod_set="vanilla",
        ))
        self.assertIn(result.final_status, (STATUS_PASS, STATUS_WARN),
                      msg=result.report)
        self.assertIsNotNone(result.blueprint_string)
        self.assertLessEqual(len(result.iterations), 3)
        # The plan must produce >= 30/s of iron-plate.
        self.assertEqual(result.mod_compat["missing"], [])
        self.assertEqual(result.mod_compat["disabled"], [])

    def test_vanilla_rejects_modded_entity(self):
        """A blueprint containing a modded entity is rejected when mod_set=vanilla.

        We use the static substitute table to make sure promethium-belts is
        recognised as 'not vanilla' even when it's enabled in the user
        install (the policy is what matters, not the user's state).
        """
        bp = _hand_blueprint([
            {"entity_number": 1, "name": "promethium-transport-belt",
             "position": {"x": 0.5, "y": 0.5}, "direction": 4},
        ])
        modset = mod_compat.ModSet(
            enabled={"base", "promethium-belts"},
            dlc={"space-age", "quality", "elevated-rails"},
            source="(test)",
        )
        report = mod_compat.check_compat(
            mod_compat.required_mods_for(bp), modset,
            attribution=mod_compat.attribute_blueprint(bp),
            mod_set_policy="vanilla",
        )
        self.assertIn("promethium-belts", report.missing,
                      msg=f"expected promethium-belts in missing under vanilla policy, got {report}")
        # And the substitute table should suggest turbo-transport-belt.
        self.assertEqual(report.substitutes.get("promethium-transport-belt"),
                         "turbo-transport-belt")


class InspectionTest(unittest.TestCase):
    def test_promethium_belts_reports_state_correctly(self):
        """A blueprint with promethium-transport-belt reports the mod's state."""
        bp = _hand_blueprint([
            {"entity_number": 1, "name": "promethium-transport-belt",
             "position": {"x": 0.5, "y": 0.5}, "direction": 4},
        ])
        # Three modset scenarios.
        for state, modset in (
            ("enabled", mod_compat.ModSet(enabled={"promethium-belts"}, source="(test)")),
            ("disabled", mod_compat.ModSet(disabled={"promethium-belts"}, source="(test)")),
            ("zip-only", mod_compat.ModSet(installed_zip_only={"promethium-belts"}, source="(test)")),
            ("missing", mod_compat.ModSet(source="(test)")),
        ):
            report = mod_compat.inspect_blueprint(bp, modset=modset)
            self.assertIn("promethium-belts", report.compat.required)
            self.assertEqual(modset.state_of("promethium-belts"), state)
            rendered = report.render()
            # The rendered text should reflect the state.
            if state == "enabled":
                self.assertIn("enabled", rendered.lower())
            elif state == "disabled":
                self.assertIn("disabled", rendered)
            elif state == "missing":
                self.assertIn("NOT INSTALLED", rendered)

    def test_unknown_entity_marked_not_installed(self):
        """A fictional entity has no source mod and is reported as unknown."""
        bp = _hand_blueprint([
            {"entity_number": 1, "name": "super-widget-9000",
             "position": {"x": 0, "y": 0}},
        ])
        report = mod_compat.inspect_blueprint(
            bp, modset=mod_compat.ModSet(source="(test)"),
        )
        self.assertEqual(len(report.compat.unknown_entities), 1)
        self.assertEqual(report.compat.unknown_entities[0].name, "super-widget-9000")
        rendered = report.render()
        self.assertIn("super-widget-9000", rendered)
        self.assertIn("Unknown entities", rendered)


class VanillaSubstituteTest(unittest.TestCase):
    def test_known_substitutes(self):
        self.assertEqual(
            mod_compat.vanilla_substitute("promethium-transport-belt"),
            "turbo-transport-belt",
        )
        self.assertEqual(
            mod_compat.vanilla_substitute("accumulator-mk2"),
            "accumulator",
        )

    def test_no_substitute_for_dlc(self):
        # We deliberately don't substitute DLC entities. e.g. legendary-quality
        # entities have no vanilla equivalent.
        self.assertIsNone(mod_compat.vanilla_substitute("electric-furnace"))
        self.assertIsNone(mod_compat.vanilla_substitute("not-a-real-name"))


if __name__ == "__main__":
    unittest.main()
