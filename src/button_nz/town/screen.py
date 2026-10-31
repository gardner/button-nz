"""Where on a section a granny flat may stand under Schedule 1A's siting
rules, and which real prefabs fit there.

The rules screened are the measurable ones that need no site visit: the
building stands at least ``SETBACK_M`` from every legal boundary and at least
``SEPARATION_M`` from other residential buildings, and isn't built across an
allotment boundary. Each section (one parcel) is screened on its own, so a
product never spans two parcels. Every building outline is treated as a
residential building, which can only leave less room.

A product fits if its rectangle fits inside the room (``catalogue.fit``). Its
stated dimensions rarely include eaves, and the setbacks are measured to the
outline with eaves, so each count is also made with the rectangle grown by
``EAVE_ALLOWANCE_M`` on every side.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shapely import MultiPolygon, Polygon, union_all
from shapely.geometry.base import BaseGeometry

from button_nz.catalogue import Product, fits
from button_nz.catalogue.fit import TOLERANCE_M

SETBACK_M = 2.0  # Schedule 1A: from any legal boundary
SEPARATION_M = 2.0  # Schedule 1A: from other residential buildings
EAVE_ALLOWANCE_M = 0.6  # an assumed overhang: suppliers rarely publish eaves
QUAD_SEGS = 16  # segments per quarter circle in a buffer


@dataclass(frozen=True)
class SectionResult:
    """One section's screen. Product ids are largest floor area first."""

    parcel_id: int
    area_m2: float
    buildings: int  # LINZ outlines overlapping it
    room_m2: float  # under the LINZ outlines
    fits: tuple[str, ...]
    fits_eaves: tuple[str, ...]
    clear_room_m2: float  # also clear of everything over 2 m on the LiDAR
    clear: tuple[str, ...]
    clear_eaves: tuple[str, ...]


def room(section: BaseGeometry, buildings: Sequence[BaseGeometry]) -> BaseGeometry:
    """Where a flat's outline may stand: ``SETBACK_M`` inside the section's
    boundary and ``SEPARATION_M`` from every one of ``buildings``."""
    inset = _buffer(section, -SETBACK_M)
    if not buildings:
        return inset
    return inset.difference(union_all([_buffer(b, SEPARATION_M) for b in buildings]))


def _buffer(geometry: BaseGeometry, distance: float) -> BaseGeometry:
    """``geometry`` buffered by at least ``distance`` everywhere. A buffer's
    arcs are chords inside the true circle; pushing their vertices out to
    circumscribe it means the room is never closer than ``distance``."""
    widened = distance / math.cos(math.pi / (4 * QUAD_SEGS))
    return geometry.buffer(widened, quad_segs=QUAD_SEGS)


def fitting(
    space: BaseGeometry, products: Sequence[Product], eave_m: float = 0.0
) -> tuple[str, ...]:
    """The ids of ``products`` whose outline, grown by ``eave_m`` on every
    side, fits inside some part of ``space``. Unlabelled dimensions never fit."""
    parts = polygons(space)
    found: list[Product] = []
    for p in products:
        length, width = p.length_m + 2 * eave_m, p.width_m + 2 * eave_m
        least = (length - TOLERANCE_M) * (width - TOLERANCE_M)  # what fits() needs, at least
        if p.dimensions_labelled and any(
            part.area >= least and fits(part, length, width) for part in parts
        ):
            found.append(p)
    return tuple(p.id for p in sorted(found, key=lambda p: -p.floor_area_m2))


def screen_section(
    parcel_id: int,
    section: BaseGeometry,
    buildings: Sequence[BaseGeometry],
    tall: BaseGeometry,
    products: Sequence[Product],
) -> SectionResult:
    """Screen ``section`` against the ``buildings`` around it, and again
    against ``tall``: everything the LiDAR shows over 2 m around it."""
    on_it = [b for b in buildings if b.intersection(section).area > 0]
    space = room(section, buildings)
    clear_space = space if tall.is_empty else space.difference(_buffer(tall, SEPARATION_M))
    stated = fitting(space, products)
    # Less room, or a bigger outline, can't fit more: only re-try what fitted.
    by_id = {p.id: p for p in products}
    fitted = [by_id[i] for i in stated]
    clear = fitting(clear_space, fitted)
    return SectionResult(
        parcel_id=parcel_id,
        area_m2=section.area,
        buildings=len(on_it),
        room_m2=space.area,
        fits=stated,
        fits_eaves=fitting(space, fitted, EAVE_ALLOWANCE_M),
        clear_room_m2=clear_space.area,
        clear=clear,
        clear_eaves=fitting(clear_space, [by_id[i] for i in clear], EAVE_ALLOWANCE_M),
    )


def polygons(geometry: BaseGeometry) -> list[Polygon]:
    """The polygons making up ``geometry``, whatever kind of collection it is."""
    if isinstance(geometry, Polygon):
        return [] if geometry.is_empty else [geometry]
    if isinstance(geometry, MultiPolygon):
        return [g for g in geometry.geoms if not g.is_empty]
    parts = getattr(geometry, "geoms", ())
    return [g for g in parts if isinstance(g, Polygon) and not g.is_empty]
