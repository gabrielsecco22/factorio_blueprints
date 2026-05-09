"""Layout: turn a `ProductionPlan` (or fixed-shape spec) into placed entities.

Coordinate system (matches `docs/blueprint_format.md` section 10):
- +x = east, +y = south.
- Entity `position` is the **center** of the entity's tile footprint.
  - For odd-sized footprints (1x1, 3x3, 5x5), the center has integer
    coordinates relative to a footprint whose NW corner is at (0,0).
  - For even-sized footprints (2x2, 4x4), the center is at (.5, .5).

Internally we work in **tile units**. The NW corner of the bounding
box is anchored at (0, 0) for each example, which keeps blueprint
positions small and predictable.

We build a `LayoutResult` whose `entities` list is in entity-number
order (1-based). The entity-number assignment lives here because
downstream stages (wires, schedules) reference it.

For the MVP, "direction" uses the 16-way enum (Factorio 2.0 unification,
see FFF-378): N=0, E=4, S=8, W=12. Cardinal directions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from harness import catalog
from harness.plan import ProductionCell, ProductionPlan
from harness.spec import BuildSpec

# 16-way direction enum
DIR_N = 0
DIR_E = 4
DIR_S = 8
DIR_W = 12


@dataclass
class PlacedEntity:
    """A single entity ready for blueprint serialisation."""

    entity_number: int
    name: str
    # NW-corner tile of the footprint (integer). Used for collision checks.
    nw_tile: tuple[int, int]
    footprint: tuple[int, int]  # (w, h) in tiles
    direction: int = DIR_N
    # Extra fields the encoder copies into the blueprint entity verbatim.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def position(self) -> dict[str, float]:
        """Blueprint `position` for this entity.

        Convention (verified against `tools/blueprint_codec.py` self-test):

            position = NW_tile + tile_size/2 - 0.5

        That gives integer positions for odd-sided footprints (1x1, 3x3,
        5x5) and half-integer positions for even-sided ones (2x2, 4x4).
        Emit ints as ints so the JSON matches what the game emits.
        """
        x, y = self.nw_tile
        w, h = self.footprint
        cx = x + (w - 1) / 2.0
        cy = y + (h - 1) / 2.0
        # If the result is a whole number, emit an int (matches game style).
        cx_out: float | int = int(cx) if cx == int(cx) else cx
        cy_out: float | int = int(cy) if cy == int(cy) else cy
        return {"x": cx_out, "y": cy_out}

    def covered_tiles(self) -> Iterable[tuple[int, int]]:
        x, y = self.nw_tile
        w, h = self.footprint
        for dx in range(w):
            for dy in range(h):
                yield (x + dx, y + dy)


@dataclass
class LayoutResult:
    entities: list[PlacedEntity] = field(default_factory=list)
    occupied: dict[tuple[int, int], int] = field(default_factory=dict)  # tile -> entity_number
    warnings: list[str] = field(default_factory=list)
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)  # min_x, min_y, max_x, max_y exclusive

    def next_entity_number(self) -> int:
        return len(self.entities) + 1

    def place(
        self,
        name: str,
        nw_tile: tuple[int, int],
        *,
        direction: int = DIR_N,
        footprint: Optional[tuple[int, int]] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> PlacedEntity:
        fp = footprint if footprint is not None else catalog.footprint(name)
        ent = PlacedEntity(
            entity_number=self.next_entity_number(),
            name=name,
            nw_tile=nw_tile,
            footprint=fp,
            direction=direction,
            extra=extra or {},
        )
        for tile in ent.covered_tiles():
            if tile in self.occupied:
                other = self.entities[self.occupied[tile] - 1]
                raise LayoutError(
                    f"placement collision: {name} at tile {tile} overlaps "
                    f"existing {other.name} (entity_number {other.entity_number})"
                )
            self.occupied[tile] = ent.entity_number
        self.entities.append(ent)
        # Update bbox.
        x, y = nw_tile
        w, h = fp
        if not self.entities:  # never true here, but keeps form
            self.bbox = (x, y, x + w, y + h)
        else:
            min_x, min_y, max_x, max_y = self.bbox
            if len(self.entities) == 1:
                self.bbox = (x, y, x + w, y + h)
            else:
                self.bbox = (
                    min(min_x, x),
                    min(min_y, y),
                    max(max_x, x + w),
                    max(max_y, y + h),
                )
        return ent


class LayoutError(ValueError):
    """Raised when placement is impossible."""


# ---------------------------------------------------------------------------
# Smelter array
# ---------------------------------------------------------------------------
#
# Layout sketch (example for a 4-furnace stone-furnace array):
#
#   row y          col 0    col 2    col 4    col 6
#                  ^ furnaces are 2x2; each occupies tiles (col..col+1, row..row+1)
#
#       y = -1     B B B B B B B B   <- top belt:  output (plates flow east)
#       y =  0     ^ ^ ^ ^ ^ ^ ^ ^   <- one inserter per furnace facing N (drop on belt)
#       y =  1     [F F][F F][F F]...
#       y =  2     [F F][F F][F F]...
#       y =  3     v v v v v v v v   <- one inserter per furnace facing S (pickup ore)
#       y =  4     B B B B B B B B   <- bottom belt: ore feed (flowing east)
#
# In the burner-furnace case we add a fuel-feed inserter on the belt's
# downstream side (east) of each furnace -- but the simplest design is
# to interleave fuel onto the same input belt every N tiles. For the
# MVP we keep both belts as ore-only and use the fact that fuel needs
# to be supplied separately as a documented limitation; the array is
# still a valid blueprint, just under-fueled. Fuel-feed will land in
# v2.

def layout_smelter_array(plan: ProductionPlan, spec: BuildSpec) -> LayoutResult:
    if len(plan.cells) != 1:
        raise LayoutError("smelter_array layout expects exactly one cell")
    cell = plan.cells[0]
    n = cell.count
    machine_fp = catalog.footprint(cell.machine)
    if machine_fp[0] != machine_fp[1]:
        raise LayoutError("smelter_array assumes a square machine footprint")
    fw = machine_fp[0]
    fh = machine_fp[1]
    # Spacing: machines are placed contiguously side-by-side.
    layout = LayoutResult()

    belt_name = spec.belt_tier
    inserter_name = spec.inserter_tier

    # Geometry rows (y values, top-down).
    # The output belt sits one tile above the inserter; the inserter sits
    # one tile above the furnace. For 2x2 furnaces (h=2) this gives:
    #   y=-1: output belt
    #   y= 0: top-side inserter (drops onto furnace top tile? no, picks
    #          up from furnace and drops on belt. So inserter at y=0
    #          picks up at y=1 (furnace) and drops at y=-1 (belt).)
    # Each inserter occupies y=0 and y = fh+1; the inserter's tile is
    # adjacent to the belt and adjacent to the furnace.
    output_belt_y = -1
    output_inserter_y = 0
    machine_top_y = 1
    machine_bot_y = machine_top_y + fh - 1
    input_inserter_y = machine_top_y + fh
    input_belt_y = input_inserter_y + 1

    # x layout: machines side-by-side starting at x=0.
    # We add one extra belt tile on each end so the belt extends past the
    # furnaces, which makes pasting in-game tidier.
    total_width = n * fw

    # Top output belt (flows east -> direction E). Span [0, total_width).
    for x in range(total_width):
        layout.place(belt_name, (x, output_belt_y), direction=DIR_E)

    # For each furnace: place inserter (drop onto belt, facing N), then furnace,
    # then bottom inserter (drop onto furnace, facing N from belt), then bottom belt.
    for i in range(n):
        x = i * fw
        # Furnaces are placed with NW corner at (x, machine_top_y).
        machine_extra: dict[str, Any] = {}
        # Burner furnaces don't need a recipe; furnaces auto-pick by ingredient.
        layout.place(cell.machine, (x, machine_top_y))

        # Output inserter centered above the furnace (x_center = x + fw/2 - 0.5
        # for 2x2 -> x+0). For 1-wide inserter we want the column under the
        # belt that aligns with the furnace center column. The 2x2 furnace
        # spans columns [x, x+1]; we put the inserter at column x (left of
        # center -- both columns work). Direction N = drops at y_center-1.
        ins_x = x + fw // 2  # center-ish column
        # Output inserter: pickup from furnace (south side of inserter),
        # drop on output belt (north side). Direction N means inserter's
        # output is at y-1, input is at y+1, with the inserter at output_inserter_y.
        layout.place(inserter_name, (ins_x, output_inserter_y), direction=DIR_N)

        # Input inserter: pickup from belt (south side, at y=input_belt_y),
        # drop on furnace (north side, at y=machine_bot_y). Direction N
        # gives drop=y-1, pickup=y+1. Inserter sits at y=input_inserter_y.
        layout.place(inserter_name, (ins_x, input_inserter_y), direction=DIR_N)

    # Bottom input belt (flows east). Span [0, total_width).
    for x in range(total_width):
        layout.place(belt_name, (x, input_belt_y), direction=DIR_E)

    return layout


# ---------------------------------------------------------------------------
# Solar field
# ---------------------------------------------------------------------------
#
# Layout: we tile solar panels in a rectangular grid, then place
# accumulators in a row to the east. Every solar panel and accumulator
# must be within a pole's supply area. We use medium-electric-pole
# (3.5-tile supply radius -> 7x7 supply square) interleaved every 5
# columns so all 3x3 panels are covered.
#
#   Sketch (panels = P, accumulators = A, medium poles = M):
#
#       P P P  P P P  M  A
#       P P P  P P P  M  A
#       P P P  P P P  M  A
#                        A
#                        A
#
# We pack panels tightly (3x3 each, no gaps) and place a medium pole
# every 6 tiles in x at the bottom-right corner. Accumulators sit
# directly east of the panel block.

def layout_solar_field(plan: ProductionPlan, spec: BuildSpec) -> LayoutResult:
    """Lay out a solar field with full pole coverage.

    A medium-electric-pole has a 7x7 tile supply square centred on its
    1x1 footprint. With 3x3 panels packed contiguously, a pole gap of
    1 tile between groups of TWO panels gives full coverage:

        x:  0 1 2  3 4 5  6  7 8 9  10 11 12 ...
            [P P P][P P P][M][P P P][P  P  P ][M] ...
            ^----- 6 tiles -----^   ^--- 6 ----^
        pole at x=6 has center (6.5, *), covers x-centers in [3.0, 10.0]
        -> panel centers at 1.5, 4.5, 7.5, 10.5; covers 4.5 and 7.5
        -> panels at x=[0..2] and x=[9..11] are NOT covered by this pole.

    OK: with one pole per 2-panel block, the pattern needs the pole
    BETWEEN panel groups, and we need to add a pole column at the very
    start and end of every panel row too.

    Pattern used here (M = pole column, P = 3-tile panel column):

        x:  0  1 2 3  4 5 6  7  8 9 10  11 12 13  14
           [M][P P P][P P P][M][P P P ][P  P  P ][M]
            covers      covers      covers
            x in       x in        x in
            [-3,3]     [4,10]      [11,17]

        Pole at x=0 covers panels at x=[1..3] (c=2.5) and x=[4..6] (c=5.5)
                                           IN          IN
        Pole at x=7 covers panels at x=[4..6] (c=5.5) and x=[8..10] (c=9.5)
                                           IN          IN
        Pole at x=14 covers panels at x=[8..10] (c=9.5) and x=[11..13] (c=12.5)
                                            IN          IN

    So every panel column is covered. Vertical spacing follows the same
    rule: every 7 rows (3+3+1) place a pole row. For the MVP we keep panel
    columns coupled to pole columns: pole rows at y in {0, 7, 14, ...}
    cover panel rows at y in {1..3, 4..6, ...}.

    Accumulators sit east of the last pole column with the same pattern.
    """
    panels_cell = next((c for c in plan.cells if c.machine == "solar-panel"), None)
    accs_cell = next((c for c in plan.cells if c.machine == "accumulator"), None)
    if panels_cell is None or accs_cell is None:
        raise LayoutError("solar_field plan must contain both solar-panel and accumulator cells")

    n_panels = panels_cell.count
    n_accs = accs_cell.count

    layout = LayoutResult()

    PANEL = 3
    # Panel block: pick a roughly-square arrangement.
    panel_cols = max(2, int(round(n_panels ** 0.5)))
    if panel_cols % 2:
        panel_cols += 1  # make it even so each "pair" is balanced
    panel_rows = (n_panels + panel_cols - 1) // panel_cols
    if panel_rows % 2:
        panel_rows += 1

    # Compute world x for each panel column. Pattern: pole | P P | pole | P P | pole ...
    # Pole columns at x = 0, 1+2*PANEL, 1+2*PANEL+1+2*PANEL, ...
    pole_x_positions: list[int] = []
    panel_col_x: list[int] = []  # world x for each panel index in 0..panel_cols-1
    cursor = 0
    pole_x_positions.append(cursor)
    cursor += 1
    for c in range(panel_cols):
        if c > 0 and c % 2 == 0:  # every 2 panel cols, insert pole
            pole_x_positions.append(cursor)
            cursor += 1
        panel_col_x.append(cursor)
        cursor += PANEL
    pole_x_positions.append(cursor)  # trailing pole column
    panels_block_end_x = cursor + 1  # +1 for trailing pole

    # Same pattern for y.
    pole_y_positions: list[int] = []
    panel_row_y: list[int] = []
    cursor = 0
    pole_y_positions.append(cursor)
    cursor += 1
    for r in range(panel_rows):
        if r > 0 and r % 2 == 0:
            pole_y_positions.append(cursor)
            cursor += 1
        panel_row_y.append(cursor)
        cursor += PANEL
    pole_y_positions.append(cursor)
    panels_block_end_y = cursor + 1

    # Place panels.
    placed = 0
    for r in range(panel_rows):
        for c in range(panel_cols):
            if placed >= n_panels:
                break
            nw = (panel_col_x[c], panel_row_y[r])
            layout.place("solar-panel", nw)
            placed += 1

    # Accumulators: similar pattern, east of last pole column.
    ACC = 2
    acc_origin_x = panels_block_end_x  # past the trailing pole column
    acc_cols_initial = max(2, int(round(n_accs ** 0.5)))
    if acc_cols_initial % 2:
        acc_cols_initial += 1
    acc_rows = (n_accs + acc_cols_initial - 1) // acc_cols_initial
    if acc_rows % 2:
        acc_rows += 1

    # Accumulators in pairs separated by pole columns. Each accumulator pair
    # occupies 4 tiles, plus 1 tile pole = 5 tiles. Pole at x=acc_origin_x
    # covers acc centers x in [acc_origin_x-3, acc_origin_x+3]; pair NW at
    # acc_origin_x+1 -> centers at x=2 and x=4 (in pole-relative coords) ->
    # absolute centers acc_origin_x+2 and acc_origin_x+4. Both in range.
    acc_pole_x_positions: list[int] = []
    acc_col_x: list[int] = []
    cursor = acc_origin_x  # first pole already exists at panels_block_end_x - 1; check
    # We already have a pole at pole_x_positions[-1] which is panels_block_end_x - 1.
    # That pole covers x in [pbex-4, pbex+2]. Its right edge at pbex+2 is
    # acc_origin_x+1, which covers the first accumulator pair (NW at acc_origin_x).
    # So we don't need a fresh pole column at acc_origin_x; we start the
    # accumulator block at acc_origin_x and add poles between pairs.
    for c in range(acc_cols_initial):
        if c > 0 and c % 2 == 0:
            acc_pole_x_positions.append(cursor)
            cursor += 1
        acc_col_x.append(cursor)
        cursor += ACC
    acc_pole_x_positions.append(cursor)  # trailing pole after the accumulator block

    placed = 0
    for r in range(acc_rows):
        for c in range(acc_cols_initial):
            if placed >= n_accs:
                break
            nw = (acc_col_x[c], r * ACC)
            layout.place("accumulator", nw)
            placed += 1
    accs_block_end_y = acc_rows * ACC

    # Total y-extent for pole rows in the accumulator block.
    # We use a similar pole_y_positions for accs but stepped by 5 (2+2+1 = 5).
    acc_pole_y_positions: list[int] = []
    cursor = 0
    acc_pole_y_positions.append(cursor)
    cursor += 1
    for r in range(acc_rows):
        if r > 0 and r % 2 == 0:
            acc_pole_y_positions.append(cursor)
            cursor += 1
        cursor += ACC
    acc_pole_y_positions.append(cursor)

    # Place panel-block poles.
    for px in pole_x_positions:
        for py in pole_y_positions:
            tile = (px, py)
            if tile in layout.occupied:
                continue
            layout.place("medium-electric-pole", tile)

    # Place accumulator-block poles. Reuse the panel-block trailing pole
    # column for the first accumulator-side coverage.
    for px in acc_pole_x_positions:
        for py in acc_pole_y_positions:
            tile = (px, py)
            if tile in layout.occupied:
                continue
            layout.place("medium-electric-pole", tile)

    return layout


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def layout(plan: ProductionPlan, spec: BuildSpec) -> LayoutResult:
    if spec.kind == "smelter_array":
        return layout_smelter_array(plan, spec)
    if spec.kind == "solar_field":
        return layout_solar_field(plan, spec)
    raise LayoutError(f"unknown spec.kind {spec.kind!r}")
