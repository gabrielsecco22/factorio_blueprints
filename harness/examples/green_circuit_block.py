"""Green circuit block: 4 copper-cable + 6 electronic-circuit assemblers.

Two stacked rows of assembling-machine-1, sharing a copper-cable middle
belt. Iron-plate input on the north side of the circuit row, copper-plate
input on the south side of the cable row, finished circuits leave on the
output belt directly above the circuit row.

Layout (rows running east):
    y=-2: iron-plate input belt
    y=-1: circuit output belt
    y= 0: per circuit assembler:
            - long-handed-inserter (DIR_S) at column x   (iron belt -> assembler)
            - inserter (DIR_N) at column x+2             (assembler -> output belt)
    y= 1..3: electronic-circuit assemblers (3x3, 6 of them)
    y= 4: per circuit assembler: fast-inserter (DIR_N) at column x+1
    y= 5: copper-cable middle belt
    y= 6: per cable assembler: fast-inserter (DIR_N) at column x+1
    y= 7..9: copper-cable assemblers (3x3, 4 of them)
    y=10: per cable assembler: inserter (DIR_N) at column x+1
    y=11: copper-plate input belt

Throughput (assembling-machine-1, crafting_speed=0.5):
    cable     = 0.5 * 2 / 0.5 = 2 cable/s/asm * 4 = 8 cable/s
    circuit   = 0.5 * 1 / 0.5 = 1 circuit/s/asm * 6 = 6 circuit/s
    cable demand = 6 * 3 = 18 cable/s
    -> cable supply (8) is BELOW cable demand (18); circuits will
    be cable-starved. The plan cell warning records this. The 4:6 ratio
    matches the prompt; a follow-up should switch to assembling-machine-2
    (or beacons) so cable supply matches demand.

Run as `python3 -m harness.examples.green_circuit_block`.
"""

from __future__ import annotations

import sys

from harness import BuildSpec, synthesize


def build():
    spec = BuildSpec(
        kind="green_circuit_block",
        machine_choice="assembling-machine-1",
        belt_tier="transport-belt",
        inserter_tier="inserter",
        pole_choice="substation",
        cable_assembler_count=4,
        circuit_assembler_count=6,
        label="MVP green circuit block (4 cable + 6 circuit assemblers)",
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
