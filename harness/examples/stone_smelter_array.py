"""12 stone-furnace iron-plate smelter array.

Layout (NW corner at origin):
- top row: 24 transport-belt tiles facing east (output)
- inserter row pointing N (drops plates onto top belt)
- 12 stone-furnaces, 2x2 each, packed side-by-side
- inserter row pointing N (picks ore from the bottom belt)
- bottom row: 24 transport-belt tiles facing east (input)

Throughput: stone-furnace crafting_speed=1, recipe energy 3.2 s ->
0.3125 plates/s/furnace * 12 = 3.75 plates/s. The yellow input belt
moves 15 items/s/lane, so even a single belt covers ore demand for
this tiny array.

Limitation: there is no fuel feed in v1. The user must supply coal to
each furnace manually after pasting, OR upgrade to electric-furnace and
add a substation. See `KNOWN_LIMITATIONS.md`.

Run as `python3 -m harness.examples.stone_smelter_array` to print the
blueprint string.
"""

from __future__ import annotations

import sys

from harness import BuildSpec, synthesize


def build():
    spec = BuildSpec(
        kind="smelter_array",
        target="iron-plate",
        machine_count=12,
        machine_choice="stone-furnace",
        fuel="coal",
        belt_tier="transport-belt",
        inserter_tier="burner-inserter",
        label="MVP stone smelter array (12 furnaces, fuel-feed not included)",
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
