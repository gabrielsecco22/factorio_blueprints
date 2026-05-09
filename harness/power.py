"""Electric-pole placement helpers.

Used by builders that need to retrofit power coverage onto a grid of
machines (e.g. `electric_smelter_array`). For solar fields, panel/pole
interleaving is still inline in `layout.py` because the geometry is
tightly tied to the panel block.

A pole's "supply area" is a square of side `supply_area_square_tiles`
centred on the pole's tile centre. Coverage is checked tile-by-tile in
`harness.validate.check_power_coverage` — this helper only places poles;
it doesn't compute optimal placement, just a sufficient regular grid.
"""

from __future__ import annotations

from harness import catalog
from harness.layout import LayoutResult


def cover_rect_with_poles(
    layout: LayoutResult,
    *,
    pole: str,
    nw_tile: tuple[int, int],
    width: int,
    height: int,
    step: int,
) -> int:
    """Drop poles on a regular grid covering the rectangle [nw_x..nw_x+width)
    by [nw_y..nw_y+height) tiles.

    Pole positions are at (nw_x + i*step, nw_y + j*step) for i, j >= 0
    such that the position is inside the rectangle. If a pole position
    collides with an existing entity, it is skipped (so callers can
    safely call this with overlapping rectangles).

    Returns the number of poles actually placed.
    """
    pole_w, pole_h = catalog.footprint(pole)
    if pole_w != pole_h:
        raise ValueError(f"non-square pole footprint {pole_w}x{pole_h} not supported")

    nw_x, nw_y = nw_tile
    placed = 0
    y = nw_y
    while y < nw_y + height:
        x = nw_x
        while x < nw_x + width:
            tile = (x, y)
            # Skip if any of the pole footprint tiles is occupied.
            collision = False
            for dx in range(pole_w):
                for dy in range(pole_h):
                    if (x + dx, y + dy) in layout.occupied:
                        collision = True
                        break
                if collision:
                    break
            if not collision:
                layout.place(pole, tile)
                placed += 1
            x += step
        y += step
    return placed
