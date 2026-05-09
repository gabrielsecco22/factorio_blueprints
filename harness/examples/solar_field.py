"""24 solar panels + 20 accumulators in the canonical Nauvis ratio.

Solar-panel block: 5x5 grid (25 cells, top-left 24 used; one cell skipped).
Accumulators: 4x5 column block to the east of the panels.
Power: medium-electric-poles tile the area on a 7-tile grid so every
panel and accumulator is within supply.

Run as `python3 -m harness.examples.solar_field`.
"""

from __future__ import annotations

import sys

from harness import BuildSpec, synthesize


def build():
    spec = BuildSpec(
        kind="solar_field",
        solar_panel_count=24,
        accumulator_count=20,
        label="MVP solar field (24 panels + 20 accumulators)",
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
