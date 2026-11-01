"""Which prefab products fit inside an accepted design's footprint.

A product that fits has walls no closer to any boundary, building or kept
area than the design's walls. That alone doesn't keep the design's verdicts:
the evaluator checks the outline with its eaves, and a product keeps them only
if its eaves overhang no further than the design's. The suppliers mostly don't
publish eaves, so those checks need running on the product's own outline. Its
height and floor level are not checked either.

A product's rectangle is tried square to each of the footprint's walls, and to
its minimum rotated rectangle (so a curved footprint is tried too), both ways
round. It fits if it lies inside the footprint to within ``TOLERANCE_M``. Other
orientations aren't tried: a fit can be missed, never invented.

The footprint is moved to the origin before it is turned: at NZTM magnitudes
(millions of metres) the overlay can leave zero-area slivers that look like
room. And every fit is confirmed by placing the rectangle and checking that
the footprint covers it, so an overlay artefact can't report a fit.
"""

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from shapely import MultiPoint, Polygon, box, union_all
from shapely.affinity import rotate, translate

from button_nz.catalogue.products import Product

TOLERANCE_M = 0.01  # a product this much longer and wider than its room still fits
MIN_WALL_M = 0.5  # shorter edges are corners and openings, not walls to line up with
SLACK_M = 1e-6  # float noise a confirmed placement may cross the footprint by


@dataclass(frozen=True)
class Matches:
    fits: tuple[Product, ...]  # largest floor area first
    unchecked: tuple[Product, ...]  # dimensions unlabelled: never presented as fitting


def matches(footprint: Polygon, products: Iterable[Product]) -> Matches:
    """The products that fit inside ``footprint``, and those that can't be checked."""
    products = tuple(products)
    fitting = [
        p for p in products if p.dimensions_labelled and fits(footprint, p.length_m, p.width_m)
    ]
    return Matches(
        fits=tuple(sorted(fitting, key=lambda p: -p.floor_area_m2)),
        unchecked=tuple(p for p in products if not p.dimensions_labelled),
    )


def fits(footprint: Polygon, length: float, width: float) -> bool:
    """Whether a ``length`` x ``width`` rectangle fits inside ``footprint``,
    square to one of its walls."""
    return placement(footprint, length, width) is not None


def placement(footprint: Polygon, length: float, width: float) -> Polygon | None:
    """Where a ``length`` x ``width`` rectangle stands inside ``footprint``,
    square to one of its walls, in the footprint's own coordinates; None if it
    doesn't fit. Footprints are moved to the origin first: rotating national
    grid coordinates about (0, 0) loses precision."""
    x0, y0, *_ = footprint.bounds
    moved = translate(footprint, -x0, -y0)
    for angle in _wall_angles(moved):
        turned = rotate(moved, -angle, origin=(0, 0), use_radians=True)
        for along, across in ((length, width), (width, length)):
            corner = _room_for(turned, along - TOLERANCE_M, across - TOLERANCE_M)
            if corner is not None:
                placed = box(corner[0], corner[1], corner[0] + along, corner[1] + across)
                back = rotate(placed, angle, origin=(0, 0), use_radians=True)
                return translate(back, x0, y0)
    return None


def _wall_angles(footprint: Polygon) -> list[float]:
    """The directions of the footprint's walls and of its minimum rotated
    rectangle, modulo a right angle."""
    angles: dict[int, float] = {}
    walls = [e for e in _edges(footprint) if math.dist(*e) >= MIN_WALL_M]
    rectangle = footprint.minimum_rotated_rectangle
    if isinstance(rectangle, Polygon):
        walls.append(next(_edges(rectangle)))
    for (x0, y0), (x1, y1) in walls:
        angle = math.atan2(y1 - y0, x1 - x0) % (math.pi / 2)
        angles.setdefault(round(angle * 1000), angle)
    return list(angles.values())


def _room_for(footprint: Polygon, length: float, width: float) -> tuple[float, float] | None:
    """Whether an axis-aligned ``length`` x ``width`` rectangle fits in ``footprint``:
    somewhere for its corner inside the footprint where it meets no wall. Where it
    would meet one is each edge swept by the rectangle, held by that corner. A
    corner found there counts only once the rectangle placed at it is confirmed.
    Returns that corner, or None."""
    corners = ((0.0, 0.0), (length, 0.0), (length, width), (0.0, width))
    walls = union_all(
        [
            MultiPoint([(x - dx, y - dy) for x, y in edge for dx, dy in corners]).convex_hull
            for edge in _edges(footprint)
        ]
    )
    leftover = footprint.difference(walls)
    candidates = getattr(leftover, "geoms", (leftover,))
    holder = footprint.buffer(SLACK_M)
    for part in sorted(candidates, key=lambda g: -g.area):
        if part.area <= 0:
            break  # lines and points: overlay artefacts, never room
        corner = part.representative_point()
        if holder.covers(box(corner.x, corner.y, corner.x + length, corner.y + width)):
            return (float(corner.x), float(corner.y))
    return None


def _edges(polygon: Polygon) -> Iterator[Sequence[tuple[float, float]]]:
    for ring in (polygon.exterior, *polygon.interiors):
        points = [(float(x), float(y)) for x, y, *_ in ring.coords]
        yield from zip(points, points[1:], strict=False)
