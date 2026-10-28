"""Plan shapes of a triangle mesh (the Dwelling, as ``design_measure.py``
reports it, in local metres): its outline seen from above, and horizontal
sections through it.

A section is the area a closed mesh encloses at one height: where its
triangles cross that plane, joined into rings. An open mesh leaves the rings
unclosed, so its section is empty.
"""

from collections.abc import Sequence

from shapely import LineString, MultiLineString, Polygon, polygonize, union_all
from shapely.geometry.base import BaseGeometry

type Triangle = Sequence[Sequence[float]]

MIN_AREA_M2 = 1e-6


def outline(triangles: Sequence[Triangle]) -> BaseGeometry:
    """Everything the mesh covers, seen from above."""
    shadows = [Polygon([(p[0], p[1]) for p in t]) for t in triangles]
    return union_all([s for s in shadows if s.is_valid and s.area > MIN_AREA_M2])


def outline_above(triangles: Sequence[Triangle], z: float) -> BaseGeometry:
    """What the mesh covers above height ``z``, seen from above: each triangle
    clipped at ``z`` (a roof slope reaching the floor still counts above it)."""
    shadows = [Polygon(part) for t in triangles if len(part := _clip_above(t, z)) >= 3]
    return union_all([s for s in shadows if s.is_valid and s.area > MIN_AREA_M2])


def _clip_above(triangle: Triangle, z: float) -> list[tuple[float, float]]:
    """The XY outline of the part of ``triangle`` at or above ``z``
    (Sutherland-Hodgman against the plane)."""
    kept: list[tuple[float, float]] = []
    for i in range(3):
        a, b = triangle[i], triangle[(i + 1) % 3]
        if a[2] >= z:
            kept.append((a[0], a[1]))
        if (a[2] >= z) != (b[2] >= z):
            s = (z - a[2]) / (b[2] - a[2])
            kept.append((a[0] + s * (b[0] - a[0]), a[1] + s * (b[1] - a[1])))
    return kept


def section(triangles: Sequence[Triangle], z: float) -> BaseGeometry:
    """The area the mesh encloses at height ``z`` (empty if it isn't closed there)."""
    segments = [cut for t in triangles if (cut := _cut(t, z)) is not None]
    if not segments:
        return Polygon()
    lines = union_all(MultiLineString(segments))  # noded, shared segments merged
    return union_all(list(polygonize([lines]).geoms))


def _cut(triangle: Triangle, z: float) -> LineString | None:
    """Where ``triangle`` crosses the plane at ``z``. A vertex on the plane
    counts as above it, so each crossing is found exactly once; each edge is
    taken in a fixed order, so neighbours sharing it compute the same point."""
    points: list[tuple[float, float]] = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        pa, pb = sorted((tuple(triangle[a]), tuple(triangle[b])))
        if (pa[2] < z) != (pb[2] < z):
            t = (z - pa[2]) / (pb[2] - pa[2])
            points.append((pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1])))
    if len(points) != 2 or points[0] == points[1]:
        return None
    return LineString(points)
