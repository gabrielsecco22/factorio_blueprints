"""24 electric-furnace copper-plate smelter array with substation power.

Layout:
- top row:        transport-belt facing east (output, plates flow east)
- inserter row:   plain inserter per furnace facing N (drops plates)
- 24 electric-furnaces, 3x3 each, packed side-by-side
- inserter row:   plain inserter per furnace facing N (picks ore)
- bottom row:     transport-belt facing east (copper-ore feed)
- substation row: substations (2x2, supply 18x18) two tiles south of the
                  ore belt, spaced so all furnaces and inserters are
                  inside at least one supply area.

Throughput: electric-furnace crafting_speed=2, recipe energy 3.2 s ->
0.625 plates/s/furnace * 24 = 15 plates/s. One yellow belt lane in,
one out per pair of furnaces.

Modules: NONE in this MVP. Electric furnaces have 2 module slots each
that a follow-up version should fill with productivity / speed modules
(quality-tier-aware) and add beacons.

Run as `python3 -m harness.examples.electric_smelter_array`.
"""

from __future__ import annotations

import sys

from harness import BuildSpec, synthesize


def build():
    spec = BuildSpec(
        kind="electric_smelter_array",
        target="copper-plate",
        machine_count=24,
        machine_choice="electric-furnace",
        belt_tier="transport-belt",
        inserter_tier="inserter",
        pole_choice="substation",
        label="MVP electric smelter array (24 furnaces, substation power)",
    )
    return synthesize(spec)


def main() -> int:
    result = build()
    sys.stdout.write(result.report)
    sys.stdout.write("\n\n")
    sys.stdout.write("## Blueprint string\n\n")
    sys.stdout.write(result.blueprint_string)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
