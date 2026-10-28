"""Terrain sampling shared by the Blender scripts. Pure Python (no bpy), so it
runs inside Blender and is tested outside it.

A height grid is ``scene_input``'s: ``rows`` x ``cols`` samples at cell centres,
row-major from the north edge, with ``(x0, y0)`` the north-west sample.
"""

import math
from typing import Any


def height_at(grid: dict[str, Any], x: float, y: float) -> float:
    """The terrain surface height at (x, y), on the same triangles as the terrain
    mesh (``terrain_faces``), so anything placed with it sits on the rendered
    ground exactly. Points beyond the outer centres take the edge height."""
    cell, cols, rows = grid["cell_m"], grid["cols"], grid["rows"]
    col = min(max((x - grid["x0"]) / cell, 0.0), cols - 1.0)
    row = min(max((grid["y0"] - y) / cell, 0.0), rows - 1.0)
    h = grid["heights"]
    if cols == 1 or rows == 1:
        return float(h[int(row) * cols + int(col)])
    c0, r0 = min(int(col), cols - 2), min(int(row), rows - 2)
    fc, fr = col - c0, row - r0

    def at(r: int, c: int) -> float:
        return float(h[(r0 + r) * cols + c0 + c])

    # Each cell is split along its north-west to south-east diagonal.
    if fr >= fc:  # south-west triangle: NW, SW, SE
        return at(0, 0) + fr * (at(1, 0) - at(0, 0)) + fc * (at(1, 1) - at(1, 0))
    return at(0, 0) + fc * (at(0, 1) - at(0, 0)) + fr * (at(1, 1) - at(0, 1))  # NW, SE, NE


def terrain_faces(rows: int, cols: int) -> list[tuple[int, int, int]]:
    """Triangles of the terrain mesh over a row-major vertex grid: each cell split
    along its north-west to south-east diagonal, as ``height_at`` assumes."""
    faces: list[tuple[int, int, int]] = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            nw, ne, sw, se = (
                r * cols + c,
                r * cols + c + 1,
                (r + 1) * cols + c,
                (r + 1) * cols + c + 1,
            )
            faces += [(nw, sw, se), (nw, se, ne)]
    return faces


def mesh_crossings(ring: list[list[float]], grid: dict[str, Any]) -> list[tuple[float, float]]:
    """The ring's corners plus every point where its edges cross an edge of the
    terrain mesh's triangles (vertical and horizontal grid lines through the
    cell centres, and the NW-SE diagonals). Each segment between consecutive
    points then lies inside one flat triangle, so a polyline through them,
    lifted by a constant, follows the rendered ground exactly."""
    cell, x0, y0 = grid["cell_m"], grid["x0"], grid["y0"]
    points: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        c1, r1 = (x1 - x0) / cell, (y0 - y1) / cell
        c2, r2 = (x2 - x0) / cell, (y0 - y2) / cell
        ts = {0.0}
        for a, b in ((c1, c2), (r1, r2), (c1 - r1, c2 - r2)):  # columns, rows, diagonals
            ts |= _integer_crossings(a, b)
        points += [(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t) for t in sorted(ts)]
    return [*points, (ring[-1][0], ring[-1][1])]


def _integer_crossings(a: float, b: float) -> set[float]:
    """Parameters t in (0, 1) where a + t (b - a) is a whole number."""
    if a == b:
        return set()
    low, high = sorted((a, b))
    return {(k - a) / (b - a) for k in range(math.floor(low) + 1, math.ceil(high))}
