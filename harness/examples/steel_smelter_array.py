"""24 steel-furnace iron-plate smelter array with shared-belt fuel feed.

Layout (NW corner near origin):
- top row: transport-belt facing east (output, plates flow east)
- inserter row: one burner-inserter per furnace facing N (drops plates)
- 24 steel-furnaces, 2x2 each, packed side-by-side
- inserter row: TWO burner-inserters per furnace facing N
    - left column  -> ore feed (no filter)
    - right column -> coal feed (filter=coal)
- bottom row: transport-belt facing east (input, ore + coal lane-mixed)

Throughput: steel-furnace crafting_speed=2, recipe energy 3.2 s ->
0.625 plates/s/furnace * 24 = 15 plates/s, exactly half of a yellow belt
(30 items/s) on a single lane. Two-array stack saturates a yellow belt.

Fuel feed: shared-belt mode. The user must run two lanes on the input
belt: iron-ore on one side, coal on the other. The right-column burner
inserter is filtered for coal so it only picks coal regardless of which
lane it lands on.

Run as `python3 -m harness.examples.steel_smelter_array`.
"""

from __future__ import annotations

import sys

from harness import BuildSpec, synthesize


def build():
    spec = BuildSpec(
        kind="smelter_array",
        target="iron-plate",
        machine_count=24,
        machine_choice="steel-furnace",
        fuel="coal",
        belt_tier="transport-belt",
        inserter_tier="burner-inserter",
        fuel_feed="shared",
        label="MVP steel smelter array (24 furnaces, shared-belt fuel feed)",
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
