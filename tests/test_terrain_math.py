"""Tests for button_nz.blender_worker.terrain_math (pure Python, used inside Blender)."""

import pytest

from button_nz.blender_worker.terrain_math import densify, height_at, terrain_faces


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
    for x, y in densify(ring, 0.5):
        assert height_at(grid, x, y) == pytest.approx(0.4 * x)


def test_points_beyond_the_outer_centres_are_clamped() -> None:
    grid = plane(4, 4, 1.0)
    assert height_at(grid, 0.0, 2.0) == pytest.approx(0.5)  # west of the first centre
    assert height_at(grid, 9.0, 2.0) == pytest.approx(3.5)  # east of the last


def test_densify_keeps_the_corners_and_spacing() -> None:
    points = densify([[0.0, 0.0], [2.0, 0.0], [2.0, 1.0]], 0.5)
    assert points == [
        (0.0, 0.0),
        (0.5, 0.0),
        (1.0, 0.0),
        (1.5, 0.0),
        (2.0, 0.0),
        (2.0, 0.5),
        (2.0, 1.0),
    ]


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
