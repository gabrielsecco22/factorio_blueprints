"""Belt + inserter wiring helpers shared across builders.

The MVP layouts each ran their own inline belt/inserter loops. As we
add more builders we lift the common patterns here so each example can
stay short and declarative. None of these helpers do anything magical;
they just call `LayoutResult.place` in a loop with consistent direction
choices.
"""

from __future__ import annotations

from typing import Any, Optional

from harness.layout import (
    DIR_E,
    DIR_N,
    DIR_S,
    DIR_W,
    LayoutResult,
)


def lay_horizontal_belt(
    layout: LayoutResult,
    *,
    belt_name: str,
    y: int,
    x_start: int,
    x_end: int,
    direction: int = DIR_E,
) -> None:
    """Place transport-belt tiles along row `y` from x_start to x_end (exclusive)."""
    for x in range(x_start, x_end):
        layout.place(belt_name, (x, y), direction=direction)


def place_inserter_pair(
    layout: LayoutResult,
    *,
    inserter_name: str,
    column: int,
    output_y: int,
    input_y: int,
) -> None:
    """Place a furnace-style inserter pair: one DIR_N at output_y (machine -> belt
    above), one DIR_N at input_y (belt below -> machine).

    Caller is responsible for ensuring the rows above output_y and below input_y
    hold belts.
    """
    layout.place(inserter_name, (column, output_y), direction=DIR_N)
    layout.place(inserter_name, (column, input_y), direction=DIR_N)


def place_filtered_inserter(
    layout: LayoutResult,
    *,
    inserter_name: str,
    nw_tile: tuple[int, int],
    direction: int,
    filter_item: str,
) -> None:
    """Place an inserter with a single-item filter (e.g. coal fuel feeder).

    Filter format follows `specs/blueprint_schema.json` $defs.entity.filters:
    a list of {index, name, quality?} items.
    """
    extra: dict[str, Any] = {
        "filters": [{"index": 1, "name": filter_item}],
        "use_filters": True,
    }
    layout.place(inserter_name, nw_tile, direction=direction, extra=extra)
