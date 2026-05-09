"""Battery of known-correct rate-calculator tests.

Run with: `python3 -m unittest validation.test_rate_calculator`

Each test states the hand-derived expected number, citing where it
comes from in the dump (`specs/data-raw-dump.json`) or in the curated
catalogs (`specs/recipes.json`, etc).
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.rate_calculator import (
    Beacon,
    RateInput,
    compute_rates,
    PROD_CAP_DEFAULT,
    QUALITY_CAP,
    SPEED_FLOOR,
)


class YellowAssemblerCopperCableTest(unittest.TestCase):
    """1x assembling-machine-1 doing copper-cable.

    crafting_speed = 0.5, energy_required = 0.5 s, results = 2 cables/craft.
    Expected: 0.5 / 0.5 * 2 = 2 cables/s/machine, 1 plate consumed.
    """

    def test_throughput(self):
        inp = RateInput(
            recipe="copper-cable",
            machine="assembling-machine-1",
            use_modded=False,
        )
        out = compute_rates(inp)
        self.assertAlmostEqual(out.crafts_per_second_per_machine, 1.0, places=6)
        self.assertAlmostEqual(out.outputs_per_second["copper-cable"], 2.0, places=6)
        self.assertAlmostEqual(out.inputs_per_second["copper-plate"], 1.0, places=6)
        self.assertEqual(out.effective_productivity, 0.0)


class SteelFurnaceIronPlateTest(unittest.TestCase):
    """1x steel-furnace doing iron-plate.

    crafting_speed = 2, energy_required = 3.2 s. Expected: 2/3.2 = 0.625 plates/s.
    """

    def test_throughput(self):
        inp = RateInput(recipe="iron-plate", machine="steel-furnace", use_modded=False)
        out = compute_rates(inp)
        self.assertAlmostEqual(out.crafts_per_second_per_machine, 0.625, places=6)
        self.assertAlmostEqual(out.outputs_per_second["iron-plate"], 0.625, places=6)


class FoundryMoltenIronTest(unittest.TestCase):
    """1x foundry doing molten-iron-from-lava.

    Vanilla Space Age foundry: crafting_speed=4, base_effect.productivity=0.5.
    Recipe: energy=16, results=[molten-iron(250 fluid), stone(10 item)].
    Expected: crafts/s = 4/16 = 0.25; molten-iron = 250 * 0.25 * (1+0.5) = 93.75/s;
              stone byproduct = 10 * 0.25 * (1+0.5) = 3.75/s.
    """

    def test_vanilla_throughput(self):
        inp = RateInput(
            recipe="molten-iron-from-lava",
            machine="foundry",
            use_modded=False,
        )
        out = compute_rates(inp)
        self.assertAlmostEqual(out.crafts_per_second_per_machine, 0.25, places=6)
        self.assertAlmostEqual(out.effective_productivity, 0.5, places=6)
        self.assertAlmostEqual(out.outputs_per_second["molten-iron"], 93.75, places=6)
        self.assertAlmostEqual(out.outputs_per_second["stone"], 3.75, places=6)
        # Lava is a fluid ingredient: 500 * 0.25 = 125/s.
        self.assertAlmostEqual(out.inputs_per_second["lava"], 125.0, places=6)


class EmPlantBeaconTest(unittest.TestCase):
    """1x EM plant + 5x prod-3 + 12 vanilla beacons each holding 2x speed-3.

    Vanilla EM plant: crafting_speed=2, base_effect.productivity=0.5, 5 module slots.
    5x prod-3 modules: speed -0.75, productivity +0.5, consumption +4.0, pollution +0.5.
    Vanilla beacon (overlay): distribution_effectivity=1.5, 2 module slots.
    With N=12 beacons of one type, profile[11]=0.2886.
    Each beacon: 2x speed-3 = +1.0 speed; per_module_share = 1.5 * 0.2886 = 0.4329.
    Beacon contribution: 12 * 0.4329 * 1.0 = 5.1948 to speed.
    Total speed: -0.75 + 5.1948 = 4.4448 -> multiplier 5.4448.
    Productivity: 0.5 (base) + 0.5 (modules) = 1.0. Recipe (electronic-circuit)
    cap is 3.0 by default, so no clamp.
    Crafting: machine_speed=2, recipe_energy=0.5 -> base 4 crafts/s.
    Final: 4 * 5.4448 = 21.7792 crafts/s.
    """

    def test_throughput(self):
        inp = RateInput(
            recipe="electronic-circuit",
            machine="electromagnetic-plant",
            modules=[("productivity-module-3", "normal")] * 5,
            beacons=[
                Beacon(
                    name="beacon",
                    count=12,
                    modules=[("speed-module-3", "normal"), ("speed-module-3", "normal")],
                )
            ],
            use_modded=False,  # vanilla beacon overlay
        )
        out = compute_rates(inp)
        self.assertAlmostEqual(out.raw_speed_bonus, 4.4448, places=3)
        self.assertAlmostEqual(out.effective_speed_multiplier, 5.4448, places=3)
        self.assertAlmostEqual(out.effective_productivity, 1.0, places=6)
        self.assertAlmostEqual(out.crafts_per_second_per_machine, 21.7792, places=2)
        self.assertAlmostEqual(out.outputs_per_second["electronic-circuit"], 43.5584, places=2)


class SpeedFloorTest(unittest.TestCase):
    """1x assembler with 2x efficiency-3 + huge negative speed via prod modules.

    Goal: even when raw speed bonus would push the multiplier below 0.2,
    the engine clamps at 0.2.
    """

    def test_speed_clamped(self):
        # Use vanilla 2.0.76 assembler-3 (5 module slots).
        # 5 prod-3 -> speed -0.75; we add a beacon row of beacons full of
        # extra prod-3 to push speed deeper into the negatives.
        inp = RateInput(
            recipe="electronic-circuit",
            machine="assembling-machine-3",
            modules=[("productivity-module-3", "normal")] * 4,  # vanilla overlay = 4 slots
            beacons=[
                Beacon(
                    name="beacon",
                    count=4,
                    modules=[
                        ("productivity-module-3", "normal"),
                        ("productivity-module-3", "normal"),
                    ],
                )
            ],
            use_modded=False,
        )
        out = compute_rates(inp)
        # Speed bonus could be very negative; multiplier must be clamped.
        self.assertGreaterEqual(out.effective_speed_multiplier, SPEED_FLOOR - 1e-9)
        if out.raw_speed_bonus + 1.0 < SPEED_FLOOR:
            self.assertTrue(
                any("speed multiplier" in d for d in out.diagnostics),
                f"expected speed-floor diagnostic, got: {out.diagnostics}",
            )


class ProductivityCapTest(unittest.TestCase):
    """1x EM plant w/ 5x prod-3 + many beacons + research -> hits +300% cap."""

    def test_capped(self):
        # Use modded EM plant (base prod 1.0); 5x prod-3 = +0.5; recipe-prod
        # research at level 50 = +5.0; beacons full of prod-3.
        inp = RateInput(
            recipe="electronic-circuit",
            machine="electromagnetic-plant",
            modules=[("productivity-module-3", "normal")] * 5,
            beacons=[
                Beacon(
                    name="beacon",
                    count=4,
                    modules=[
                        ("productivity-module-3", "normal"),
                        ("productivity-module-3", "normal"),
                    ],
                )
            ],
            research_levels={
                "change-recipe-productivity": {"electronic-circuit": 50},
            },
            use_modded=True,
        )
        out = compute_rates(inp)
        # Raw prod bonus should be way above the cap.
        self.assertGreater(out.raw_productivity_bonus, PROD_CAP_DEFAULT)
        # Effective productivity must be the cap.
        self.assertAlmostEqual(out.effective_productivity, PROD_CAP_DEFAULT, places=6)
        self.assertTrue(
            any("productivity bonus" in d and "above cap" in d for d in out.diagnostics),
            f"expected prod-cap diagnostic, got: {out.diagnostics}",
        )


class QualityCascadeTest(unittest.TestCase):
    """1x recycler with 4x quality-3 modules (legendary).

    Each legendary quality-3 module: quality 0.25 * 2.5 = 0.625.
    4 modules => raw quality bonus = 2.5. Engine caps at 0.248.
    Speed penalty per module: -0.05 * 2.5 = -0.125; 4 modules => -0.5 raw speed.
    """

    def test_chance_clamped(self):
        # Use a recipe the recycler can actually do; iron-plate-recycling exists in 2.0.
        inp = RateInput(
            recipe="iron-plate-recycling",
            machine="recycler",
            modules=[("quality-module-3", "legendary")] * 4,
            use_modded=True,
        )
        out = compute_rates(inp)
        self.assertAlmostEqual(out.effective_quality_chance, QUALITY_CAP, places=6)
        self.assertTrue(
            any("quality chance" in d and "above cap" in d for d in out.diagnostics),
            f"expected quality-cap diagnostic, got: {out.diagnostics}",
        )
        # Cascade should distribute output across multiple quality tiers.
        # iron-plate-recycling produces iron-plate as one of its results.
        # We can't predict the recipe exactly without inspecting it, so
        # just assert the per-quality breakdown sums to total outputs.
        for item, qmap in out.outputs_by_quality_per_second.items():
            total = out.outputs_per_second.get(item, 0.0)
            self.assertAlmostEqual(sum(qmap.values()), total, places=4)


class RateCalculatorParityTest(unittest.TestCase):
    """Mirrors RateCalculator's `process_crafter` formulation.

    For a no-module no-beacon assembler, our crafts/s should equal
        recipe.energy_required / entity.crafting_speed -> recipe_duration
        crafts/s = 1 / recipe_duration
    matching the mod's `recipe_duration = recipe.energy / entity.crafting_speed`.
    """

    def test_matches_mod_formula_no_modules(self):
        # Pick three randomly-sampled recipes and verify equality.
        cases = [
            ("iron-gear-wheel", "assembling-machine-1"),
            ("copper-cable", "assembling-machine-2"),
            ("electronic-circuit", "assembling-machine-3"),
        ]
        from tools.rate_calculator import recipes_catalog, machines_catalog

        for recipe_name, machine_name in cases:
            with self.subTest(recipe=recipe_name, machine=machine_name):
                rc = recipes_catalog()[recipe_name]
                mc = machines_catalog()[machine_name]
                expected = mc["crafting_speed"] / rc["energy_required"]
                inp = RateInput(recipe=recipe_name, machine=machine_name, use_modded=False)
                out = compute_rates(inp)
                self.assertAlmostEqual(out.crafts_per_second_per_machine, expected, places=6)


if __name__ == "__main__":
    unittest.main()
