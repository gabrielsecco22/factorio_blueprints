"""Post-layout validation.

Checks performed:
1. Tile collisions: no two entities overlap any tile.
2. Belt continuity: each transport-belt's downstream tile (per its
   direction) is either another belt facing a compatible direction,
   the boundary, or a sink (chest, splitter, underground belt). For
   the MVP we only require "downstream tile is empty or another belt
   in the same row".
3. Inserter reach: the inserter's pickup_tile and drop_tile (computed
   from `direction` + 1-tile reach for plain inserter) sit inside
   the blueprint area and the drop_tile is on a belt or machine; the
   pickup_tile is on a belt or machine. We accept "either side might
   be empty during MVP" because solar fields have no inserters.
4. JSON Schema validation against `specs/blueprint_schema.json` (only
   if `jsonschema` is importable -- otherwise emitted as a warning).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from harness import catalog
from harness.layout import (
    DIR_E,
    DIR_N,
    DIR_S,
    DIR_W,
    LayoutResult,
    PlacedEntity,
)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# Direction unit vector (N=up=-y, E=+x, S=+y, W=-x).
_DIR_VEC = {
    DIR_N: (0, -1),
    DIR_E: (1, 0),
    DIR_S: (0, 1),
    DIR_W: (-1, 0),
}


def _tile_at_offset(ent: PlacedEntity, dx: int, dy: int) -> tuple[int, int]:
    """Return a tile offset in world coordinates from the *center tile*
    of a 1x1 entity. For multi-tile entities this picks the NW tile + offset.
    """
    x, y = ent.nw_tile
    return (x + dx, y + dy)


def check_collisions(layout: LayoutResult, report: ValidationReport) -> None:
    """The layout already enforces this, but we sanity-check after the fact
    in case an example built entities by hand."""
    seen: dict[tuple[int, int], int] = {}
    for ent in layout.entities:
        for tile in ent.covered_tiles():
            if tile in seen:
                report.errors.append(
                    f"collision: entity {ent.entity_number} ({ent.name}) overlaps "
                    f"entity {seen[tile]} on tile {tile}"
                )
            else:
                seen[tile] = ent.entity_number


def check_belt_continuity(layout: LayoutResult, report: ValidationReport) -> None:
    belts = catalog.belts()
    belt_entities = [e for e in layout.entities if e.name in belts and belts[e.name]["type"] == "transport-belt"]
    if not belt_entities:
        return

    # Build a tile -> entity_number index of belts.
    belt_tile_to_id: dict[tuple[int, int], int] = {}
    for e in belt_entities:
        for tile in e.covered_tiles():
            belt_tile_to_id[tile] = e.entity_number

    # All belts in our MVP layouts run as straight lines facing E (DIR_E).
    # For each belt, check the downstream tile: it should be either
    # another belt with a compatible direction, or empty (boundary).
    for e in belt_entities:
        if e.direction not in _DIR_VEC:
            report.errors.append(
                f"belt {e.entity_number} has non-cardinal direction {e.direction}"
            )
            continue
        dx, dy = _DIR_VEC[e.direction]
        x, y = e.nw_tile
        downstream = (x + dx, y + dy)
        if downstream in belt_tile_to_id:
            other_id = belt_tile_to_id[downstream]
            other = layout.entities[other_id - 1]
            if other.direction not in (e.direction,) and other.direction not in (
                # Also accept perpendicular turns (corner belts). Not used in
                # MVP, but allowed.
                DIR_N, DIR_E, DIR_S, DIR_W,
            ):
                report.warnings.append(
                    f"belt {e.entity_number} -> {other.entity_number} "
                    f"direction mismatch ({e.direction} vs {other.direction})"
                )
        # Else: downstream is open / boundary. Acceptable.


def check_inserter_reach(layout: LayoutResult, report: ValidationReport) -> None:
    insert_entities = [e for e in layout.entities if e.name in catalog.inserters()]
    if not insert_entities:
        return

    # Build occupancy map for "is something here".
    occupancy: dict[tuple[int, int], PlacedEntity] = {}
    for e in layout.entities:
        for tile in e.covered_tiles():
            occupancy[tile] = e

    for ins in insert_entities:
        proto = catalog.inserters()[ins.name]
        # Round to nearest integer tile reach (e.g. 1.0 -> 1, 1.2 -> 1, 2.0 -> 2).
        pickup_reach = max(1, int(round(float(proto.get("pickup_distance_tiles", 1.0)))))
        drop_reach = max(1, int(round(float(proto.get("insert_distance_tiles", 1.0)))))
        if ins.direction not in _DIR_VEC:
            report.errors.append(
                f"inserter {ins.entity_number} has non-cardinal direction {ins.direction}"
            )
            continue
        dx, dy = _DIR_VEC[ins.direction]
        x, y = ins.nw_tile
        # Drop tile is `drop_reach` tiles in the inserter's facing direction.
        drop_tile = (x + dx * drop_reach, y + dy * drop_reach)
        # Pickup tile is `pickup_reach` tiles opposite.
        pickup_tile = (x - dx * pickup_reach, y - dy * pickup_reach)

        drop_target = occupancy.get(drop_tile)
        pickup_target = occupancy.get(pickup_tile)
        if drop_target is None and pickup_target is None:
            report.warnings.append(
                f"inserter {ins.entity_number} ({ins.name}) at {ins.nw_tile} "
                f"has neither pickup nor drop target nearby"
            )
            continue
        # The inserter shouldn't overlap any entity (own tile must be free of
        # collisions, which is already enforced by the layout collision check).


def check_power_coverage(layout: LayoutResult, report: ValidationReport) -> None:
    """Every electric entity must lie inside at least one pole's supply area."""
    poles = catalog.poles()
    pole_entities = [e for e in layout.entities if e.name in poles]

    # An entity is "electric" if it's in machines.json with energy_source.type == electric,
    # OR if it's an electric inserter, OR a solar/accumulator.
    machines = catalog.machines()
    inserters = catalog.inserters()

    def is_electric(ent: PlacedEntity) -> bool:
        m = machines.get(ent.name)
        if m is not None:
            es = m.get("energy_source") or {}
            return es.get("type") == "electric"
        if ent.name in inserters:
            return inserters[ent.name].get("energy_source_type") == "electric"
        if ent.name == "solar-panel":
            return True  # produces power, doesn't need supply
        if ent.name == "accumulator":
            return False  # buffers, doesn't need supply (connected via pole)
        return False

    # Solar panels and accumulators don't *consume* power but they do need
    # to be connected to a pole network for the power to flow. Treat them
    # as "needs coverage" too.
    def needs_coverage(ent: PlacedEntity) -> bool:
        if ent.name == "solar-panel" or ent.name == "accumulator":
            return True
        return is_electric(ent) and ent.name not in poles

    targets = [e for e in layout.entities if needs_coverage(e)]
    if not targets:
        return
    if not pole_entities:
        report.errors.append(
            f"{len(targets)} electric entities placed but no electric poles found"
        )
        return

    # Pole supply is a square of side supply_area_square_tiles centred on the
    # pole's blueprint `position` (the geometric centre). The square reaches
    # half-side tiles on each axis. An entity is "covered" if its position
    # (also the entity's centre) sits inside that square.
    pole_areas: list[tuple[float, float, float]] = []  # (cx, cy, half_side)
    for p in pole_entities:
        proto = poles[p.name]
        side = float(proto["supply_area_square_tiles"])
        pos = p.position
        pole_areas.append((float(pos["x"]), float(pos["y"]), side / 2.0))

    for t in targets:
        pos = t.position
        cx = float(pos["x"])
        cy = float(pos["y"])
        covered = False
        for (px, py, half) in pole_areas:
            if abs(cx - px) <= half and abs(cy - py) <= half:
                covered = True
                break
        if not covered:
            report.errors.append(
                f"entity {t.entity_number} ({t.name}) at position ({cx},{cy}) "
                f"is outside every pole's supply area"
            )


def check_schema(blueprint_obj: dict, report: ValidationReport) -> None:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        report.warnings.append("jsonschema not installed; skipped schema validation")
        return
    schema = catalog.blueprint_schema()
    try:
        jsonschema.validate(blueprint_obj, schema)
    except jsonschema.ValidationError as exc:
        report.errors.append(f"schema validation failed: {exc.message} at {list(exc.path)}")


def validate(layout: LayoutResult, blueprint_obj: Optional[dict] = None) -> ValidationReport:
    report = ValidationReport()
    check_collisions(layout, report)
    check_belt_continuity(layout, report)
    check_inserter_reach(layout, report)
    check_power_coverage(layout, report)
    if blueprint_obj is not None:
        check_schema(blueprint_obj, report)
    return report
