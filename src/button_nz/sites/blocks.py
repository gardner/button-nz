"""A title's land in blocks: the pieces of it that touch (#136).

A road can cut a title in two: in Reefton's old town grid, lanes cross whole
sections, and LINZ then gives each parcel as a MultiPolygon. A site is one
block of land, so it is built on one block: the one its address is on, or for
a title with no address, the one its parcel is on. The rest is left out,
and said to be.
"""

from collections.abc import Sequence
from typing import Any, cast

from shapely import Point as ShapelyPoint
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from button_nz.geo.arcgis import Feature
from button_nz.geo.geometry import Point

TOUCH_M = 0.05  # pieces this close share a boundary: LINZ's shared edges, to rounding


def pieces(parcels: Sequence[Feature]) -> list[Feature]:
    """Every parcel as Polygon pieces: itself, or each part of a MultiPolygon,
    with the parcel's properties."""
    found: list[Feature] = []
    for parcel in parcels:
        geometry = cast("dict[str, Any]", parcel["geometry"])
        if geometry.get("type") != "MultiPolygon":
            found.append(parcel)
            continue
        for part in cast("list[Any]", geometry["coordinates"]):
            found.append({**parcel, "geometry": {"type": "Polygon", "coordinates": part}})
    return found


def parcels_in(found: Sequence[Feature]) -> int:
    """How many parcels the pieces ``found`` are of: a MultiPolygon's parts count once."""
    return len({cast("dict[str, Any]", f["properties"])["id"] for f in found})


def block(parcels: Sequence[Feature], point: Point) -> tuple[list[Feature], float]:
    """The pieces of the title's block of land holding ``point`` (the nearest
    if none does), and the area, in m², of the title's land left out."""
    parts = pieces(parcels)
    if not parts:
        return [], 0.0
    shapes = [shape(cast("dict[str, Any]", p["geometry"])) for p in parts]
    blocks = _touching(shapes)
    area = [sum(shapes[i].area for i in b) for b in blocks]
    at = ShapelyPoint(point)
    chosen = min(range(len(blocks)), key=lambda k: min(shapes[i].distance(at) for i in blocks[k]))
    return [parts[i] for i in sorted(blocks[chosen])], sum(area) - area[chosen]


def _touching(shapes: Sequence[BaseGeometry]) -> list[list[int]]:
    """``shapes``' indices grouped into blocks that touch, each a chain of
    pieces within ``TOUCH_M`` of the next."""
    group = list(range(len(shapes)))

    def root(i: int) -> int:
        while group[i] != i:
            i = group[i]
        return i

    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            if shapes[i].distance(shapes[j]) <= TOUCH_M:
                group[root(j)] = root(i)
    found: dict[int, list[int]] = {}
    for i in range(len(shapes)):
        found.setdefault(root(i), []).append(i)
    return list(found.values())
