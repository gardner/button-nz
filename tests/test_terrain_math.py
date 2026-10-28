"""Tests for button_nz.blender_worker.terrain_math (pure Python, used inside Blender)."""

import pytest

from button_nz.blender_worker.terrain_math import height_at, mesh_crossings, terrain_faces


def plane(rows: int, cols: int, slope: float) -> dict[str, object]:
    """Cell-centre heights of a plane rising ``slope`` m/m east; x0, y0 = 0.5, rows-0.5."""
    heights = [slope * (c + 0.5) for _ in range(rows) for c in range(cols)]
    return {
        "rows": rows,
        "cols": cols,
        "cell_m": 1.0,
        "x0": 0.5,
        "y0": rows - 0.5,
        "heights": heights,
    }


def test_heights_between_centres_follow_the_surface() -> None:
    grid = plane(20, 30, 0.4)
    ring = [[5.0, 5.0], [25.0, 5.0], [25.0, 15.0], [5.0, 15.0], [5.0, 5.0]]
    for x, y in mesh_crossings(ring, grid):
        assert height_at(grid, x, y) == pytest.approx(0.4 * x)


def test_points_beyond_the_outer_centres_are_clamped() -> None:
    grid = plane(4, 4, 1.0)
    assert height_at(grid, 0.0, 2.0) == pytest.approx(0.5)  # west of the first centre
    assert height_at(grid, 9.0, 2.0) == pytest.approx(3.5)  # east of the last


def test_heights_follow_the_mesh_triangles_not_a_bilinear_surface() -> None:
    """In a saddle cell the two differ most; the mesh splits each cell along the
    north-west to south-east diagonal, and height_at must use the same triangles."""
    grid = {
        "rows": 2,
        "cols": 2,
        "cell_m": 1.0,
        "x0": 0.5,
        "y0": 1.5,
        "heights": [0.0, 1.0, 1.0, 0.0],
    }
    assert height_at(grid, 1.0, 1.0) == pytest.approx(0.0)  # on the diagonal: 0 -> 0
    assert height_at(grid, 1.25, 1.25) == pytest.approx(0.5)  # NE triangle (0, 1, 0)
    assert height_at(grid, 0.75, 0.75) == pytest.approx(0.5)  # SW triangle (0, 1, 0)


def test_terrain_faces_share_the_diagonal_height_at_uses() -> None:
    assert terrain_faces(2, 3) == [(0, 3, 4), (0, 4, 1), (1, 4, 5), (1, 5, 2)]


def test_boundary_segments_lie_on_single_mesh_triangles() -> None:
    """Points at every crossing of the mesh's triangle edges keep each straight
    segment inside one flat triangle, so it follows the ground exactly, even
    for a ring off the grid over a one-cell ridge."""
    rows, cols = 20, 30
    heights = [2.0 if c == 15 else 0.0 for _ in range(rows) for c in range(cols)]
    grid = {
        "rows": rows,
        "cols": cols,
        "cell_m": 1.0,
        "x0": 0.5,
        "y0": rows - 0.5,
        "heights": heights,
    }
    ring = [[5.25, 5.3], [25.25, 5.3], [25.25, 15.3], [5.25, 15.3], [5.25, 5.3]]
    points = mesh_crossings(ring, grid)
    assert points[0] == (5.25, 5.3) and points[-1] == (5.25, 5.3)
    for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
        midpoint = height_at(grid, (x1 + x2) / 2, (y1 + y2) / 2)
        chord = (height_at(grid, x1, y1) + height_at(grid, x2, y2)) / 2
        assert chord == pytest.approx(midpoint, abs=1e-9)
    assert max(height_at(grid, x, y) for x, y in points) == pytest.approx(
        2.0
    )  # the ridge is sampled
