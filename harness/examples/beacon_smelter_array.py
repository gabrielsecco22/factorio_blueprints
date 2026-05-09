"""12 electric-furnace iron-plate smelter array with vanilla beacons.

Layout (NW corner near origin):
- y=-9..-8: not used
- y=-7..-6: substation row N        (3 substations, supply 18x18 covers everything north)
- y=-5..-3: beacon row N             (12 vanilla beacons, packed 3 tiles apart)
- y=-2:     output belt              (transport belt, plates flow east)
- y=-1:     output inserter row      (one inserter per furnace, DIR_N)
- y= 0..2:  12 electric-furnaces     (3x3 each, packed = 36 tiles wide)
- y= 3:     input inserter row       (one inserter per furnace, DIR_N)
- y= 4:     input belt               (transport belt, ore flows east)
- y= 5..7:  beacon row S             (12 vanilla beacons, packed)
- y= 8..9:  substation row S         (3 substations, supply 18x18 covers everything south)

Beacon configuration:
- 24 vanilla beacons total (12 N + 12 S, packed every 3 tiles)
- Each vanilla beacon: 2 module slots, supply_area_distance=3, distribution_effectivity=1.5,
  energy_usage=480 kW
- Each beacon holds 2x speed-module-3 (+50% speed each)
- Each electric-furnace holds 2x productivity-module-3 (vanilla 2-slot overlay)

Per-machine beacon coverage formula:
- A beacon at NW=(bx, beacon_row_y) supplies tiles in [bx-3, bx+5] x
  [beacon_row_y-3, beacon_row_y+5]. With beacons packed every 3 tiles
  along the furnace row, the beacons whose supply x-range intersects a
  furnace at NW=(fx, 0) (covering x=fx..fx+2) are those with
  bx in {fx-3, fx, fx+3} - i.e. up to 3 beacons per row, 6 total
  (3 N + 3 S) for inner furnaces.
- Edge furnaces (i=0 and i=11) lose one neighbour and end up under 4
  beacons each.

Throughput: with 6 beacons * 2 speed-3 each (raw 1.0 per beacon),
distribution_effectivity 1.5, profile[5] = 0.4082, the speed multiplier is
1 + 6 * 1.5 * 0.4082 ~= 4.67. Furnace base 0.625 plates/s -> ~2.92 plates/s.
Productivity-module-3 in the furnace adds +20% raw productivity (2 slots *
+10% each); recipe `iron-plate` allows productivity, so output rate gets a
+20% multiplier: ~3.7 plates/s per inner furnace.

We use fast-transport-belt (60 items/s total) to handle the ~44 plates/s
total throughput on the output side.

Run as `python3 -m harness.examples.beacon_smelter_array`.
"""

from __future__ import annotations

import sys

from harness import BuildSpec, synthesize


def build():
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
        label="Beacon smelter array (12 electric-furnaces, 24 vanilla beacons)",
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
