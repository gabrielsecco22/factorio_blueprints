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

# 16-way direction enum (FFF-378 unification).
DIR_N = 0
DIR_NE = 2
DIR_E = 4
DIR_SE = 6
DIR_S = 8
DIR_SW = 10
DIR_W = 12
DIR_NW = 14


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
    """Generic smelter-array layout for stone, steel, and electric furnaces.

    Geometry (rows running east):
        y=-1: output belt
        y= 0: output inserter row (one per furnace, DIR_N)
        y= 1..1+fh-1: furnace row (square footprint, packed contiguously)
        y= input_inserter_y: input inserter row (DIR_N)
        y= input_belt_y: input belt
        y= fuel_belt_y (optional): dedicated fuel belt + filtered inserter row

    Fuel-feed mode (only meaningful for burner furnaces; ignored otherwise):
        - None (default): no fuel feed; user must supply fuel manually.
        - "shared": one extra burner-inserter per furnace at column x+1
          of the furnace, picking up from the SAME input belt with a coal
          filter. Requires fw >= 2.
        - "separate": adds a parallel fuel belt south of the input belt.
          Each furnace gets a long-handed-inserter (still burner-fueled
          if appropriate) reaching across the input belt to the fuel
          belt. Requires fw >= 2 to keep ore inserter and fuel inserter
          from colliding.
    """
    if len(plan.cells) != 1:
        raise LayoutError("smelter_array layout expects exactly one cell")
    cell = plan.cells[0]
    n = cell.count
    machine_fp = catalog.footprint(cell.machine)
    if machine_fp[0] != machine_fp[1]:
        raise LayoutError("smelter_array assumes a square machine footprint")
    fw = machine_fp[0]
    fh = machine_fp[1]
    layout = LayoutResult()

    belt_name = spec.belt_tier
    inserter_name = spec.inserter_tier

    machines = catalog.machines()
    machine_proto = machines[cell.machine]
    energy_source = machine_proto.get("energy_source") or {}
    is_burner = energy_source.get("type") == "burner"
    fuel_feed = spec.fuel_feed
    if not is_burner:
        fuel_feed = None  # silently disable for electric furnaces

    output_belt_y = -1
    output_inserter_y = 0
    machine_top_y = 1
    input_inserter_y = machine_top_y + fh
    input_belt_y = input_inserter_y + 1
    fuel_belt_y = input_belt_y + 2  # leaves a row for the long-handed fuel inserter

    total_width = n * fw

    # Output belt.
    for x in range(total_width):
        layout.place(belt_name, (x, output_belt_y), direction=DIR_E)

    for i in range(n):
        x = i * fw
        layout.place(cell.machine, (x, machine_top_y))

        # Choose inserter columns:
        # - Output inserter at the centre-left column of the furnace.
        # - Input (ore) inserter same column.
        # - Fuel inserter (if fuel_feed is set) at centre-right column.
        out_col = x + fw // 2
        in_col = out_col
        layout.place(inserter_name, (out_col, output_inserter_y), direction=DIR_N)
        layout.place(inserter_name, (in_col, input_inserter_y), direction=DIR_N)

        if fuel_feed == "shared":
            if fw < 2:
                raise LayoutError("shared fuel feed requires furnace width >= 2")
            fuel_col = x + (fw - 1)  # right-most column of the furnace
            if fuel_col == in_col:
                fuel_col = x  # pick the other side
            from harness import wiring
            wiring.place_filtered_inserter(
                layout,
                inserter_name="burner-inserter",
                nw_tile=(fuel_col, input_inserter_y),
                direction=DIR_N,
                filter_item=spec.fuel,
            )
        elif fuel_feed == "separate":
            if fw < 2:
                raise LayoutError("separate fuel feed requires furnace width >= 2")
            fuel_col = x + (fw - 1)
            if fuel_col == in_col:
                fuel_col = x
            # Long-handed inserter at fuel_belt_y - 1 (i.e. just above the
            # fuel belt). Reaches 2 tiles north into the furnace bottom row.
            from harness import wiring
            long_y = fuel_belt_y - 1
            wiring.place_filtered_inserter(
                layout,
                inserter_name="long-handed-inserter",
                nw_tile=(fuel_col, long_y),
                direction=DIR_N,
                filter_item=spec.fuel,
            )

    # Input belt.
    for x in range(total_width):
        layout.place(belt_name, (x, input_belt_y), direction=DIR_E)

    # Fuel belt (only for "separate" feed).
    if fuel_feed == "separate":
        for x in range(total_width):
            layout.place(belt_name, (x, fuel_belt_y), direction=DIR_E)

    # Power coverage (electric_smelter_array path).
    if spec.kind == "electric_smelter_array":
        from harness import power
        pole_name = spec.pole_choice or "substation"
        pole_w, _ = catalog.footprint(pole_name)
        pole_proto = catalog.poles()[pole_name]
        supply_side = float(pole_proto["supply_area_square_tiles"])
        # Place one row of poles south of the input belt with column spacing
        # equal to supply_side (each pole's coverage diameter). The first
        # pole sits at x = max(0, (supply_side - pole_w) / 2 - 0.5) so its
        # supply area covers x=0.
        pole_y = input_belt_y + 2
        # Center spacing = supply_side, so NW spacing = supply_side as well.
        first_x = max(0, int(supply_side // 2 - pole_w))
        # Walk east placing poles until coverage reaches total_width.
        x = first_x
        while True:
            tile = (x, pole_y)
            if tile not in layout.occupied:
                layout.place(pole_name, tile)
            # Pole center x:
            center_x = x + (pole_w - 1) / 2.0
            coverage_east = center_x + supply_side / 2.0
            if coverage_east >= total_width - 0.5:
                break
            x += int(supply_side)
        # Sanity: also make sure the array's vertical extent is covered.
        # Pole row at pole_y has center y = pole_y + (pole_h-1)/2; its
        # north coverage reaches pole_center_y - supply_side/2. For
        # output_belt_y = -1 with substation supply 18 we need
        # center_y - 9 <= -1 -> center_y <= 8. pole_y + 0.5 <= 8 -> pole_y <= 7.5.
        # input_belt_y + 2 = 5+2 = 7 for 3x3 furnaces. ✓

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

# ---------------------------------------------------------------------------
# Green circuit block
# ---------------------------------------------------------------------------
#
# Two assembler rows sharing a copper-cable middle belt:
#
#       y=-2: iron-plate input belt (east)
#       y=-1: circuit output belt (east)
#       y= 0: per circuit assembler:
#             - long-handed-inserter at column x   (DIR_S): iron belt -> assembler
#             - inserter at column x+2             (DIR_N): assembler -> output belt
#       y= 1..3: circuit assembler row (3x3 each, packed)
#       y= 4: per circuit assembler: fast-inserter at column x+1 (DIR_N)
#       y= 5: copper-cable middle belt (east)
#       y= 6: per cable assembler: fast-inserter at column x+1 (DIR_N)
#       y= 7..9: cable assembler row (3x3 each, packed)
#       y=10: per cable assembler: inserter at column x+1 (DIR_N)
#       y=11: copper-plate input belt (east)
#
# Power: substations at the four corners of the bounding rectangle (NW
# (0,-4), (W-2,-4), (0,12), (W-2,12)) supply the entire block.

def layout_green_circuit_block(plan: ProductionPlan, spec: BuildSpec) -> LayoutResult:
    cable_cell = next((c for c in plan.cells if c.recipe == "copper-cable"), None)
    circuit_cell = next((c for c in plan.cells if c.recipe == "electronic-circuit"), None)
    if cable_cell is None or circuit_cell is None:
        raise LayoutError("green_circuit_block plan must contain cable and circuit cells")

    asm = cable_cell.machine
    asm_fp = catalog.footprint(asm)
    if asm_fp != (3, 3):
        raise LayoutError(f"green_circuit_block expects 3x3 assemblers, got {asm_fp} for {asm}")
    AW = 3

    n_cable = cable_cell.count
    n_circuit = circuit_cell.count

    layout = LayoutResult()
    belt_name = spec.belt_tier
    inserter_name = spec.inserter_tier  # plain inserter for input/output

    iron_belt_y = -2
    circuit_out_belt_y = -1
    circuit_top_y = 1            # circuit row spans y=1..3
    cable_inserter_top_y = 4
    middle_belt_y = 5
    cable_inserter_bot_y = 6
    cable_top_y = 7              # cable row spans y=7..9
    copper_inserter_y = 10
    copper_belt_y = 11

    width = max(n_cable, n_circuit) * AW

    # Belts (each spans the full bounding width so the layout is rectangular).
    for x in range(width):
        layout.place(belt_name, (x, iron_belt_y), direction=DIR_E)
        layout.place(belt_name, (x, circuit_out_belt_y), direction=DIR_E)
        layout.place(belt_name, (x, middle_belt_y), direction=DIR_E)
        layout.place(belt_name, (x, copper_belt_y), direction=DIR_E)

    # Circuit assembler row.
    circuit_recipe_extra = {"recipe": "electronic-circuit"}
    for i in range(n_circuit):
        x = i * AW
        layout.place(asm, (x, circuit_top_y), extra=dict(circuit_recipe_extra))
        # Iron-plate input via long-handed-inserter at column x (drops at y=2).
        layout.place(
            "long-handed-inserter",
            (x, 0),
            direction=DIR_S,
        )
        # Circuit output via plain inserter at column x+2 (DIR_N).
        layout.place(inserter_name, (x + 2, 0), direction=DIR_N)
        # Cable input via fast-inserter at column x+1 (DIR_N from middle belt).
        layout.place("fast-inserter", (x + 1, cable_inserter_top_y), direction=DIR_N)

    # Cable assembler row.
    cable_recipe_extra = {"recipe": "copper-cable"}
    for i in range(n_cable):
        x = i * AW
        layout.place(asm, (x, cable_top_y), extra=dict(cable_recipe_extra))
        # Cable output via fast-inserter at column x+1 (DIR_N: pickup from
        # cable assembler at y=7, drop on middle belt at y=5).
        layout.place("fast-inserter", (x + 1, cable_inserter_bot_y), direction=DIR_N)
        # Copper-plate input via plain inserter at column x+1 (DIR_N: pickup
        # from copper belt at y=11, drop into cable assembler at y=9).
        layout.place(inserter_name, (x + 1, copper_inserter_y), direction=DIR_N)

    # Power. Place substations at the four corners. With supply 18x18 they
    # cover the whole 14-tile-tall block.
    pole_name = spec.pole_choice or "substation"
    pole_w, pole_h = catalog.footprint(pole_name)
    if pole_name != "substation":
        # For non-substation poles the corner-only layout will not cover
        # the full block; fall back to a regular grid via power.cover_rect.
        from harness import power
        power.cover_rect_with_poles(
            layout,
            pole=pole_name,
            nw_tile=(0, iron_belt_y - 2),
            width=width,
            height=copper_belt_y + 2 - (iron_belt_y - 2),
            step=int(catalog.poles()[pole_name]["supply_area_square_tiles"]),
        )
    else:
        # Corners outside the bbox so they don't collide with belts.
        north_y = iron_belt_y - 2  # y = -4
        south_y = copper_belt_y + 1  # y = 12
        east_x = max(0, width - pole_w)
        for nw in [(0, north_y), (east_x, north_y), (0, south_y), (east_x, south_y)]:
            if nw not in layout.occupied:
                layout.place(pole_name, nw)

    return layout


def layout(plan: ProductionPlan, spec: BuildSpec) -> LayoutResult:
    if spec.kind == "smelter_array" or spec.kind == "electric_smelter_array":
        return layout_smelter_array(plan, spec)
    if spec.kind == "solar_field":
        return layout_solar_field(plan, spec)
    if spec.kind == "green_circuit_block":
        return layout_green_circuit_block(plan, spec)
    raise LayoutError(f"unknown spec.kind {spec.kind!r}")
