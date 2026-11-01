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

STEP_M = 0.25  # the grid the rectangles are found on
QUAD_SEGS = 16
LINE_M = 0.05  # how wide a line between sections is taken out of the room
INSET_M = 0.01  # printed corners are drawn in this far: rounding never takes them out
MIN_WIDTH_M = 3.0  # narrower than this, no dwelling fits: not offered


@dataclass(frozen=True)
class Rectangle:
    polygon: Polygon  # NZTM (or whatever the room was in)
    length_m: float  # its long side
    width_m: float


def room_of(
    title: Sequence[Ring], buildings: Sequence[Ring], keep_clear: Sequence[Ring]
) -> BaseGeometry:
    """Where a dwelling's outline may stand under the evaluator's rules, on the
    owner's decisions: inside the setbacks, 2 m from the buildings they listed,
    off the areas they keep clear. What they chose to ignore doesn't count;
    nothing the survey found constrains a design until someone confirms it."""
    land = union_all([Polygon(ring) for ring in title])
    # A dwelling is never built across a line between a title's sections
    # (s 42B fails it); nearer than 2 m is the evaluator's "unknown", left in.
    lines = union_all([Polygon(ring).boundary for ring in title]).difference(
        land.boundary.buffer(1e-6)
    )
    inner = _buffer(land, -MIN_SEPARATION_M).difference(lines.buffer(LINE_M))
    taken = [_buffer(Polygon(r), MIN_SEPARATION_M) for r in buildings]
    taken += [Polygon(r) for r in keep_clear]
    return inner.difference(union_all(taken)) if taken else inner


def _buffer(geometry: BaseGeometry, distance: float) -> BaseGeometry:
    """``geometry`` buffered by at least ``distance`` everywhere: a buffer's arcs
    are chords inside the true circle, so their vertices are pushed out to
    circumscribe it (as ``town.screen`` does)."""
    widened = distance / math.cos(math.pi / (4 * QUAD_SEGS))
    return geometry.buffer(widened, quad_segs=QUAD_SEGS)


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
    edged = turned.buffer(1e-6)  # a corner on the room's edge is in it
    inside = _whole_cells(edged, xs, ys)
    least = math.ceil(MIN_WIDTH_M / STEP_M - 1e-9)
    found: list[Rectangle] = []
    for _ in range(count):
        cells = _largest(inside, least)
        if cells is None:
            break
        row0, col0, rows, cols = cells
        inside[row0 : row0 + rows, col0 : col0 + cols] = False
        x0, y0 = west + col0 * STEP_M, south + row0 * STEP_M
        flat = box(x0, y0, x0 + cols * STEP_M, y0 + rows * STEP_M)
        polygon = rotate(flat, angle_deg, origin=centre)
        sides = sorted((cols * STEP_M, rows * STEP_M))
        found.append(Rectangle(polygon, sides[1], sides[0]))
    return found


def _whole_cells(
    room: BaseGeometry, xs: NDArray[np.float64], ys: NDArray[np.float64]
) -> NDArray[np.bool_]:
    """The cells (centred at ``xs`` x ``ys``) lying wholly in ``room``: a kept
    area's corner poking into a cell between its corners rules it out too."""
    half = STEP_M / 2
    cx, cy = np.meshgrid(xs, ys)
    cells = shapely.box(cx - half, cy - half, cx + half, cy + half)
    shapely.prepare(room)
    covered: NDArray[np.bool_] = shapely.covers(room, cells)
    return covered


def _largest(grid: NDArray[np.bool_], least: int) -> tuple[int, int, int, int] | None:
    """The largest all-true rectangle of cells at least ``least`` cells each
    way: (row, column, rows, columns), by the histogram method, row by row.
    It visits every maximal rectangle, so a larger narrow one never hides a
    smaller one wide enough."""
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
                if top >= least and col - left >= least and top * (col - left) > best_area:
                    best_area = top * (col - left)
                    best = (row - top + 1, left, top, col - left)
            stack.append(col)
    return best


def describe_room(site: SiteContext, local: Callable[[Point], Point]) -> str:
    """The room on ``site`` and its largest rectangles for the design agent, in
    its local coordinates, with what to do with them."""
    title = site.parcels
    room = room_of(title, site.confirmed_buildings, site.preservation_areas)
    found = largest_rectangles(room, longest_edge_angle(title))
    if not found:
        return "- room for a dwelling: none left inside the rules.\n"
    lines = [
        f"- room for a dwelling ({room.area:.0f} m²: inside the setbacks, 2 m from the "
        "listed buildings, off the kept areas). Its largest rectangles, for the whole "
        "outline seen from above (eaves included), local x, y corners:"
    ]
    lines.append(rectangles_text(found, local))
    lines.append(
        "  Prefer a simple rectangular plan placed in this room; move the dwelling rather "
        "than cut a corner off it to fit, unless the brief asks for another shape."
    )
    return "\n".join(lines) + "\n"


def rectangles_text(found: Sequence[Rectangle], local: Callable[[Point], Point]) -> str:
    """Each rectangle's size and local corners, drawn in by ``INSET_M`` so a
    corner rounded to the centimetre still lies in the room."""
    lines: list[str] = []
    for i, rect in enumerate(found, 1):
        drawn = rect.polygon.buffer(-INSET_M, join_style="mitre")
        corners = _corners(drawn, local)
        long, short = _sides(corners)
        text = ", ".join(f"({x:.2f}, {y:.2f})" for x, y in corners)
        lines.append(f"  - {i}: {long:.1f} x {short:.1f} m: {text}")
    return "\n".join(lines)


def _sides(corners: Sequence[Point]) -> tuple[float, float]:
    """The rectangle's sides, long first, rounded down to 0.1 m: a printed
    size is never more than the room between its printed corners."""
    sides = sorted(math.dist(corners[i], corners[i + 1]) for i in range(2))
    return (math.floor(sides[1] * 10 + 1e-9) / 10, math.floor(sides[0] * 10 + 1e-9) / 10)


def _corners(polygon: Polygon, local: Callable[[Point], Point]) -> list[Point]:
    return [local((float(x), float(y))) for x, y in list(polygon.exterior.coords)[:-1]]
