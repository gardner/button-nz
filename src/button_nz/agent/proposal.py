"""Turn what Blender measured of the model's ``Dwelling`` into a Proposal.

The evaluator only ever sees geometry measured from the built scene, never the
model's description of it. From the Dwelling's triangles come its outline seen
from above (eaves included), the outside of its external walls (a horizontal
section ``WALL_SECTION_M`` above the floor), its floor (its lowest point,
which must be a floor spanning those walls, not a pile or a step) and its top.
A courtyard the walls enclose that is open to the sky is not floor: it is cut
out of the walls' footprint. A room inside them has a roof over it, so it is.

Problems with the model's script (an exception, no ``Dwelling``, a footprint in
pieces, an open mesh, something below the floor) are ``DesignError``s:
feedback for the model's next attempt, not crashes.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from shapely import MultiPolygon, Polygon, union_all
from shapely.geometry.base import BaseGeometry

from button_nz.agent.sections import Triangle, faces, outline, outline_above, section
from button_nz.evaluation import Proposal
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring

WALL_SECTION_M = 1.0  # where the walls are cut: above the floor, below the eaves
LOW_SECTION_M = 0.5  # and again nearer the floor, for walls that lean in
CONTAINS_TOLERANCE_M = 0.01
FLOOR_SECTION_M = 0.05  # just above the lowest point: the floor, if that's what it is
MIN_FLOOR_COVER = 0.9  # of the wall footprint
OPENING_M = 1.25  # gaps in the walls up to twice this wide (doors, garage doors) are found
OPENING_SHARE = 0.05  # of the walls' area: closing over openings may add no more
MIN_SOLIDITY = 0.5  # of the walls' convex hull: L, T and U plans pass, open strips don't
MIN_ROOM_M2 = 1.0  # smaller pieces of a wall section are posts or balusters
MAX_COURTYARD_SHARE = 0.5  # of what the walls enclose: open to the sky beyond this is no roof
COURTYARD_WALL_M = 2.0  # a courtyard's walls stand this high above the floor; a balustrade doesn't


class DesignError(ValueError):
    """The model's script did not produce a measurable dwelling."""


@dataclass(frozen=True)
class Measurements:
    """What ``design_measure.py`` measured, in the scene's local frame."""

    error: str | None
    footprint: Ring | None  # the outside of the external walls
    outline: Ring | None  # all the Dwelling covers, seen from above (eaves included)
    parts: int  # connected pieces of that outline
    z_min: float | None  # relative to the scene datum
    z_max: float | None
    floor_area_m2: float | None
    storeys: int | None
    courtyards: tuple[Ring, ...] = ()  # inside the walls and open to the sky: not floor

    def walls(self) -> Polygon | None:
        """The plan within the outside of the external walls, open courtyards cut out."""
        return None if self.footprint is None else Polygon(self.footprint, self.courtyards)


def parse_measurements(raw: Mapping[str, Any]) -> Measurements:
    """Parse ``measurements.json``: the Dwelling's triangles, in the local frame,
    become its outline, wall footprint and floor (Blender's Python has no
    shapely, so the geometry is done here)."""
    triangles = cast("list[Triangle] | None", raw.get("triangles"))
    error = cast("str | None", raw.get("error"))
    area = _dwelling_number(raw.get("floor_area_m2"), "floor_area_m2")
    storeys = _dwelling_storeys(raw.get("storeys"))
    if not triangles:
        return Measurements(error, None, None, 0, None, None, area, storeys)
    if not all(math.isfinite(c) for tri in triangles for point in tri for c in point):
        raise DesignError("Some of the Dwelling's vertices aren't finite numbers (NaN or inf).")
    heights = [float(p[2]) for t in triangles for p in t]
    z_min, z_max = min(heights), max(heights)
    plan, parts = _one_ring(outline(triangles))
    walls, courtyards = _walls(triangles, z_min, z_max) if parts == 1 else (None, ())
    return Measurements(error, walls, plan, parts, z_min, z_max, area, storeys, courtyards)


def _walls(triangles: list[Triangle], z_min: float, z_max: float) -> tuple[Ring, tuple[Ring, ...]]:
    """The outside of the external walls, checked to stand on a floor at ``z_min``:
    the larger of cuts ``WALL_SECTION_M`` and ``LOW_SECTION_M`` above the floor, so
    walls that lean in (an A-frame, a dome) are measured near the floor. And the
    courtyards open to the sky inside them, as the cut finds them."""
    cut = min(WALL_SECTION_M, (z_max - z_min) / 2)
    rooms = _rooms(triangles, z_min + cut)
    if len(rooms) != 1:
        sizes = ", ".join(f"{p.area:.0f} m²" for p in sorted(rooms, key=lambda p: -p.area))
        raise DesignError(
            f"A horizontal cut through the Dwelling {cut:g} m above its floor should cross "
            f"one closed outline of walls, but finds {len(rooms)} ({sizes or 'none'}). "
            "Make the Dwelling one closed mesh standing on its floor, its rooms joined."
        )
    walls, _ = _one_ring(rooms[0])
    if walls is None:
        raise DesignError("The Dwelling's walls don't form a closed outline.")
    courtyards = _courtyards(triangles, rooms[0], z_min + cut, z_min + _courtyard_cut(z_min, z_max))
    _check_envelope(triangles, Polygon(walls), courtyards, z_min, cut)
    rings = tuple(ring for court in courtyards if (ring := _one_ring(court)[0]) is not None)
    # Walls that lean in (an A-frame, a dome) are wider near the floor: measure them
    # there too, as far as they lean, so a deck or step beside them isn't counted.
    lower = _lower_walls(triangles, Polygon(walls), z_min, z_max, cut)
    if lower is not None:
        return lower, rings
    return walls, rings


def _courtyard_cut(z_min: float, z_max: float) -> float:
    """How high above the floor a courtyard must still be walled in."""
    return min(COURTYARD_WALL_M, (z_max - z_min) * 3 / 4)


def _courtyards(triangles: list[Triangle], walls: Polygon, z: float, high: float) -> list[Polygon]:
    """The courtyards open to the sky inside ``walls``, the section at ``z``: its
    faces clear of the walls' outside, a room's size or more, with nothing above
    most of them, and still walled in at ``high`` (a deck's balustrade isn't a
    courtyard's wall). Solid walls have their tops over them, and a room its
    roof, so neither is a courtyard. One with something a room's size standing
    in it is left as floor (the stricter reading): a courtyard is a plain hole."""
    inside = [
        face
        for face in faces(triangles, z)
        if face.area >= MIN_ROOM_M2
        and walls.contains(face.representative_point())
        and not face.intersects(walls.exterior)
        and all(Polygon(hole).area < MIN_ROOM_M2 for hole in face.interiors)
    ]
    if not inside:
        return []
    above = outline_above(triangles, z)
    open_ = [face for face in inside if face.intersection(above).area < MIN_FLOOR_COVER * face.area]
    walled = section(triangles, high)
    return [
        Polygon(court.exterior)
        for court in _pieces(union_all(open_))
        if court.intersection(walled).area >= MIN_FLOOR_COVER * court.area
    ]


def _lower_walls(
    triangles: list[Triangle], walls: Polygon, z_min: float, z_max: float, cut: float
) -> Ring | None:
    """The walls' outline ``LOW_SECTION_M`` above the floor if they lean out below
    ``cut``: the low section, kept to within the walls' own lean of their outline
    at ``cut``. The lean is estimated from how much they narrow above ``cut``."""
    low_cut = min(LOW_SECTION_M, (z_max - z_min) / 4)
    high_cut = min(cut + (cut - low_cut), (z_max - z_min) * 3 / 4)
    high = _rooms(triangles, z_min + high_cut)
    if len(high) != 1 or high_cut <= cut:
        return None
    lean = walls.hausdorff_distance(high[0]) * (cut - low_cut) / (high_cut - cut)
    if lean < CONTAINS_TOLERANCE_M:
        return None  # upright walls: the outline at ``cut`` is the footprint
    # Everything at the low cut within the walls' lean of them: a deck or step
    # further out is left behind, whether or not it touches the walls.
    low = union_all(_rooms(triangles, z_min + low_cut))
    kept = low.intersection(walls.buffer(lean, join_style="mitre"))
    around = [p for p in _pieces(kept) if p.buffer(CONTAINS_TOLERANCE_M).contains(walls)]
    if not around or around[0].area <= walls.area:
        return None
    ring, _ = _one_ring(around[0])
    return ring


def _rooms(triangles: list[Triangle], z: float) -> list[Polygon]:
    """The pieces of the section at ``z`` big enough to be rooms (not posts or balusters)."""
    return [p for p in _pieces(section(triangles, z)) if p.area >= MIN_ROOM_M2]


def _check_envelope(
    triangles: list[Triangle], walls: Polygon, courtyards: list[Polygon], z_min: float, cut: float
) -> None:
    """That ``walls`` (their outline at ``cut``) is a solid envelope: a floor under
    it and a roof over it, but for its open ``courtyards``, and no opening through it."""
    enclosed = _without(walls, courtyards)
    if enclosed.area < (1 - MAX_COURTYARD_SHARE) * walls.area:  # a shell, not a courtyard
        raise DesignError(
            f"The Dwelling has no roof over {walls.area - enclosed.area:.0f} m² of the "
            f"{walls.area:.0f} m² its walls enclose. An open courtyard may take at most "
            f"{MAX_COURTYARD_SHARE:.0%} of it: close the envelope at the top."
        )
    band = z_min + min(FLOOR_SECTION_M, cut / 2)  # faces this low are the floor's underside
    floor = outline([tri for tri in triangles if max(p[2] for p in tri) <= band])
    if floor.intersection(enclosed).area < MIN_FLOOR_COVER * enclosed.area:
        raise DesignError(
            "The Dwelling's lowest point isn't its floor: something (piles, steps, a "
            "deck or terrace) is below it. Make the underside of the floor, spanning "
            "the walls, the Dwelling's lowest point."
        )
    missing = _closed(walls).area - walls.area
    hull = walls.convex_hull.area
    if missing > max(MIN_ROOM_M2, OPENING_SHARE * walls.area) or (
        walls.area < MIN_SOLIDITY * hull  # an opening too wide to bridge
    ):
        raise DesignError(
            f"{cut:g} m above the floor the Dwelling's walls enclose only "
            f"{walls.area:.0f} m² of the {hull:.0f} m² they span: a doorway or opening "
            "breaks their outline. Model the Dwelling as a solid envelope, with no doors "
            "or windows cut through it."
        )
    if outline_above(triangles, z_min + cut).intersection(enclosed).area < (
        MIN_FLOOR_COVER * enclosed.area
    ):
        raise DesignError("The Dwelling has no roof over its walls: close the envelope at the top.")


def _without(walls: Polygon, courtyards: list[Polygon]) -> Polygon:
    """``walls`` with its open ``courtyards`` cut out (``walls`` itself if none)."""
    if not courtyards:
        return walls
    return Polygon(walls.exterior, [court.exterior for court in courtyards])


def _dwelling_number(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DesignError(f"Dwelling['{name}'] must be a number, not {value!r}.")
    return float(value)


def _dwelling_storeys(value: object) -> int | None:
    if value is None:
        return None
    whole = isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if isinstance(value, bool) or not whole:
        raise DesignError(f"Dwelling['storeys'] must be a whole number, not {value!r}.")
    return int(cast("float", value))


def to_proposal(measurements: Measurements, frame: LocalFrame, datum_m: float) -> Proposal:
    """The NZTM/NZVD2016 proposal for ``measurements``."""
    if measurements.error:
        raise DesignError(f"Your script raised an error:\n{measurements.error}")
    if measurements.parts > 1:
        raise DesignError(
            f"The Dwelling's footprint is in {measurements.parts} pieces; "
            "it must be one connected footprint."
        )
    if measurements.footprint is None or measurements.z_min is None or measurements.z_max is None:
        raise DesignError("Your script did not create a mesh object named 'Dwelling'.")
    plan = measurements.outline or measurements.footprint
    return Proposal(
        footprint=tuple(frame.to_nztm(point) for point in measurements.footprint),
        outline=tuple(frame.to_nztm(point) for point in plan),
        floor_level_m=datum_m + measurements.z_min,
        height_above_floor_m=measurements.z_max - measurements.z_min,
        floor_area_m2=measurements.floor_area_m2,
        storeys=measurements.storeys,
        courtyards=tuple(
            tuple(frame.to_nztm(point) for point in court) for court in measurements.courtyards
        ),
    )


def _closed(walls: Polygon) -> BaseGeometry:
    """``walls`` with gaps up to ``2 * OPENING_M`` bridged and the rooms behind
    them filled: the outline a solid envelope would have had."""
    bridged = walls.buffer(OPENING_M, join_style="mitre").buffer(-OPENING_M, join_style="mitre")
    return Polygon(walls.exterior).union(union_all([Polygon(p.exterior) for p in _pieces(bridged)]))


def _pieces(shape: BaseGeometry) -> list[Polygon]:
    if isinstance(shape, Polygon):
        return [] if shape.is_empty else [shape]
    if isinstance(shape, MultiPolygon):
        return list(shape.geoms)
    return []


def _one_ring(shape: BaseGeometry) -> tuple[Ring | None, int]:
    """``shape``'s outer ring if it is one polygon, and how many pieces it has."""
    if shape.is_empty:
        return None, 0
    if isinstance(shape, MultiPolygon):
        return None, len(shape.geoms)
    if not isinstance(shape, Polygon):
        return None, 0
    simple = shape.simplify(1e-6)
    if not isinstance(simple, Polygon):
        return None, 0
    return tuple((float(x), float(y)) for x, y in simple.exterior.coords), 1
