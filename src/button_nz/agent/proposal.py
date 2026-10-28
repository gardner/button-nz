"""Turn what Blender measured of the model's ``Dwelling`` into a Proposal.

The evaluator only ever sees geometry measured from the built scene, never the
model's description of it. From the Dwelling's triangles come its outline seen
from above (eaves included), the outside of its external walls (a horizontal
section ``WALL_SECTION_M`` above the floor), its floor (its lowest point,
which must be a floor spanning those walls, not a pile or a step) and its top.

Problems with the model's script (an exception, no ``Dwelling``, a footprint in
pieces, an open mesh, something below the floor) are ``DesignError``s:
feedback for the model's next attempt, not crashes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from shapely import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from button_nz.agent.sections import Triangle, outline, section
from button_nz.evaluation import Proposal
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring

WALL_SECTION_M = 1.0  # where the walls are cut: above the floor, below the eaves
FLOOR_SECTION_M = 0.05  # just above the lowest point: the floor, if that's what it is
MIN_FLOOR_COVER = 0.9  # of the wall footprint
MIN_ROOM_M2 = 1.0  # smaller pieces of a wall section are posts or balusters


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
    heights = [float(p[2]) for t in triangles for p in t]
    z_min, z_max = min(heights), max(heights)
    plan, parts = _one_ring(outline(triangles))
    walls = _walls(triangles, z_min, z_max) if parts == 1 else None
    return Measurements(error, walls, plan, parts, z_min, z_max, area, storeys)


def _walls(triangles: list[Triangle], z_min: float, z_max: float) -> Ring:
    """The outside of the external walls, checked to stand on a floor at ``z_min``."""
    cut = min(WALL_SECTION_M, (z_max - z_min) / 2)
    pieces = _pieces(section(triangles, z_min + cut))
    rooms = [p for p in pieces if p.area >= MIN_ROOM_M2]  # not posts or balusters
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
    enclosed = Polygon(walls)
    floor = section(triangles, z_min + min(FLOOR_SECTION_M, cut / 2))
    if floor.intersection(enclosed).area < MIN_FLOOR_COVER * enclosed.area:
        raise DesignError(
            "The Dwelling's lowest point isn't its floor: something (piles, steps, a "
            "deck or terrace) is below it. Make the underside of the floor, spanning "
            "the walls, the Dwelling's lowest point."
        )
    under = floor.intersection(enclosed.convex_hull).area
    if enclosed.area < MIN_FLOOR_COVER * under:
        raise DesignError(
            f"{cut:g} m above the floor the Dwelling's walls enclose only "
            f"{enclosed.area:.0f} m², but the floor within them spans {under:.0f} m²: a "
            "doorway or opening breaks their outline. Model the Dwelling as a solid "
            "envelope, with no doors or windows cut through it."
        )
    return walls


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
    )


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
