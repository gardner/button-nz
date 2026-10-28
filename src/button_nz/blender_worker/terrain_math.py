"""Terrain sampling shared by the Blender scripts. Pure Python (no bpy), so it
runs inside Blender and is tested outside it.

A height grid is ``scene_input``'s: ``rows`` x ``cols`` samples at cell centres,
row-major from the north edge, with ``(x0, y0)`` the north-west sample.
"""

import math
from typing import Any


def height_at(grid: dict[str, Any], x: float, y: float) -> float:
    """The terrain surface height at (x, y): bilinear between the four nearest
    cell centres, exactly as the terrain mesh interpolates between its
    vertices. Points beyond the outer centres take the edge height."""
    cell, cols, rows = grid["cell_m"], grid["cols"], grid["rows"]
    col = min(max((x - grid["x0"]) / cell, 0.0), cols - 1.0)
    row = min(max((grid["y0"] - y) / cell, 0.0), rows - 1.0)
    c0, r0 = min(int(col), cols - 2), min(int(row), rows - 2)
    if cols == 1 or rows == 1:
        c0, r0 = int(col), int(row)
        return float(grid["heights"][r0 * cols + c0])
    fc, fr = col - c0, row - r0
    h = grid["heights"]

    def at(r: int, c: int) -> float:
        return float(h[r * cols + c])

    top = at(r0, c0) * (1 - fc) + at(r0, c0 + 1) * fc
    bottom = at(r0 + 1, c0) * (1 - fc) + at(r0 + 1, c0 + 1) * fc
    return top * (1 - fr) + bottom * fr


def densify(ring: list[list[float]], step: float) -> list[tuple[float, float]]:
    """The ring's corners plus points at most ``step`` apart along each edge."""
    points: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / step))
        points += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n)]
    return [*points, (ring[-1][0], ring[-1][1])]
