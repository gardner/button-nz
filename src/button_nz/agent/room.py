"""Where a dwelling fits on its site, said as rectangles the design agent can use.

The room is the title less its setback, the owner's listed buildings with the
separation round them, and the areas kept clear: the same rules the evaluator
checks. Its largest rectangles, square to the title's longest edge, tell the
agent where a plain plan fits, so it can move a dwelling rather than cut a
corner off it to squeeze one in.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import shapely
from numpy.typing import NDArray
from shapely import Polygon, box, union_all
from shapely.affinity import rotate
from shapely.geometry.base import BaseGeometry

from button_nz.evaluation.checks import MIN_SEPARATION_M
from button_nz.evaluation.model import SiteContext
from button_nz.geo.geometry import Point, Ring
from button_nz.sites.heights import canopy

STEP_M = 0.25  # the grid the rectangles are found on
MIN_WIDTH_M = 3.0  # narrower than this, no dwelling fits: not offered


@dataclass(frozen=True)
class Rectangle:
    polygon: Polygon  # NZTM (or whatever the room was in)
    length_m: float  # its long side
    width_m: float


def room_of(
    title: Sequence[Ring],
    buildings: Sequence[Ring],
    keep_clear: Sequence[Ring],
    standing: Sequence[BaseGeometry] = (),
) -> BaseGeometry:
    """Where a dwelling's outline may stand under the evaluator's rules, and
    clear of what the LiDAR shows ``standing`` (a house nobody listed, a tree):
    the evaluator can't pass separation beside those, so they get the same
    room round them as a listed building."""
    inner = union_all([Polygon(ring) for ring in title]).buffer(-MIN_SEPARATION_M)
    taken = [Polygon(r).buffer(MIN_SEPARATION_M) for r in buildings]
    taken += [g.buffer(MIN_SEPARATION_M) for g in standing]
    taken += [Polygon(r) for r in keep_clear]
    return inner.difference(union_all(taken)) if taken else inner


def longest_edge_angle(title: Sequence[Ring]) -> float:
    """The direction of the title's longest edge, in degrees."""
    edges = [(a, b) for ring in title for a, b in zip(ring, ring[1:], strict=False)]
    (ax, ay), (bx, by) = max(edges, key=lambda e: math.dist(e[0], e[1]))
    return math.degrees(math.atan2(by - ay, bx - ax))


def largest_rectangles(room: BaseGeometry, angle_deg: float, count: int = 2) -> list[Rectangle]:
    """Up to ``count`` of the largest rectangles inside ``room``, square to
    ``angle_deg``, none overlapping, largest first."""
    if room.is_empty:
        return []
    centre = room.centroid
    turned = rotate(room, -angle_deg, origin=centre)
    west, south, east, north = turned.bounds
    xs = np.arange(west + STEP_M / 2, east, STEP_M)
    ys = np.arange(south + STEP_M / 2, north, STEP_M)
    inside = shapely.contains_xy(turned, *np.meshgrid(xs, ys))
    found: list[Rectangle] = []
    for _ in range(count):
        cells = _largest(inside)
        if cells is None or min(cells[2], cells[3]) * STEP_M < MIN_WIDTH_M:
            break
        row0, col0, rows, cols = cells
        inside[row0 : row0 + rows, col0 : col0 + cols] = False
        x0, y0 = west + col0 * STEP_M, south + row0 * STEP_M
        flat = box(x0, y0, x0 + cols * STEP_M, y0 + rows * STEP_M)
        polygon = rotate(flat, angle_deg, origin=centre)
        sides = sorted((cols * STEP_M, rows * STEP_M))
        found.append(Rectangle(polygon, sides[1], sides[0]))
    return found


def _largest(grid: NDArray[np.bool_]) -> tuple[int, int, int, int] | None:
    """The largest all-true rectangle of cells: (row, column, rows, columns),
    by the histogram method, row by row."""
    best: tuple[int, int, int, int] | None = None
    best_area = 0
    heights = np.zeros(grid.shape[1], dtype=int)
    for row in range(grid.shape[0]):
        heights = np.where(grid[row], heights + 1, 0)
        stack: list[int] = []
        for col in range(len(heights) + 1):
            height = heights[col] if col < len(heights) else 0
            while stack and heights[stack[-1]] >= height:
                top = int(heights[stack.pop()])
                left = stack[-1] + 1 if stack else 0
                if top * (col - left) > best_area:
                    best_area = top * (col - left)
                    best = (row - top + 1, left, top, col - left)
            stack.append(col)
    return best


def describe_room(site: SiteContext, local: Callable[[Point], Point]) -> str:
    """The room on ``site`` and its largest rectangles for the design agent, in
    its local coordinates, with what to do with them."""
    standing = [polygon for polygon, _ in canopy(site.terrain, [])]
    title = site.parcels
    room = room_of(title, site.confirmed_buildings, site.preservation_areas, standing)
    found = largest_rectangles(room, longest_edge_angle(title))
    if not found:
        return "- room for a dwelling: none left inside the rules.\n"
    lines = [
        f"- room for a dwelling ({room.area:.0f} m²: inside the setbacks, clear of listed "
        "buildings, kept areas, and anything the LiDAR shows standing over 2 m, with 2 m "
        "round each). Its largest rectangles, for the whole outline seen from above "
        "(eaves included), local x, y corners:"
    ]
    for i, rect in enumerate(found, 1):
        corners = ", ".join(f"({x:.2f}, {y:.2f})" for x, y in _corners(rect.polygon, local))
        lines.append(f"  - {i}: {rect.length_m:.1f} x {rect.width_m:.1f} m: {corners}")
    lines.append(
        "  Prefer a simple rectangular plan placed in this room; move the dwelling rather "
        "than cut a corner off it to fit, unless the brief asks for another shape."
    )
    return "\n".join(lines) + "\n"


def _corners(polygon: Polygon, local: Callable[[Point], Point]) -> list[Point]:
    return [local((float(x), float(y))) for x, y in list(polygon.exterior.coords)[:-1]]
