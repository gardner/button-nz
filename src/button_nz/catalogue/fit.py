"""Which prefab products fit inside an accepted design's footprint.

A product that fits inside the footprint is at least as far from every
boundary, building and kept area as the design the evaluator passed, so it
keeps those checks' verdicts. Its height and floor level are not checked:
the catalogue doesn't hold them.

A product's rectangle is tried square to each of the footprint's walls, both
ways round, and fits if it lies inside the footprint to within ``TOLERANCE_M``.
"""

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from shapely import MultiPoint, Polygon, union_all
from shapely.affinity import rotate

from button_nz.catalogue.products import Product

TOLERANCE_M = 0.01  # a product this much longer and wider than its room still fits
MIN_WALL_M = 0.5  # shorter edges are corners and openings, not walls to line up with


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
    for angle in _wall_angles(footprint):
        turned = rotate(footprint, -angle, origin=(0, 0), use_radians=True)
        for along, across in ((length, width), (width, length)):
            if _room_for(turned, along - TOLERANCE_M, across - TOLERANCE_M):
                return True
    return False


def _wall_angles(footprint: Polygon) -> list[float]:
    """The directions of the footprint's walls, modulo a right angle."""
    angles: dict[int, float] = {}
    for (x0, y0), (x1, y1) in _edges(footprint):
        if math.hypot(x1 - x0, y1 - y0) >= MIN_WALL_M:
            angle = math.atan2(y1 - y0, x1 - x0) % (math.pi / 2)
            angles.setdefault(round(angle * 1000), angle)
    return list(angles.values())


def _room_for(footprint: Polygon, length: float, width: float) -> bool:
    """Whether an axis-aligned ``length`` x ``width`` rectangle fits in ``footprint``:
    somewhere for its corner inside the footprint where it meets no wall. Where it
    would meet one is each edge swept by the rectangle, held by that corner."""
    corners = ((0.0, 0.0), (length, 0.0), (length, width), (0.0, width))
    walls = union_all(
        [
            MultiPoint([(x - dx, y - dy) for x, y in edge for dx, dy in corners]).convex_hull
            for edge in _edges(footprint)
        ]
    )
    return not footprint.difference(walls).is_empty


def _edges(polygon: Polygon) -> Iterator[Sequence[tuple[float, float]]]:
    for ring in (polygon.exterior, *polygon.interiors):
        points = [(float(x), float(y)) for x, y, *_ in ring.coords]
        yield from zip(points, points[1:], strict=False)
