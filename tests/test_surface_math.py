"""Tests for button_nz.blender_worker.surface_math (pure Python, used inside Blender)."""

import math
import random
from itertools import combinations

import pytest

from button_nz.blender_worker.surface_math import Point, face_uvs

WALL = ((2.0, -3.0, 0.5), (8.0, -3.0, 0.5), (8.0, -3.0, 3.5))  # faces south (-y)
ROOF = ((0.0, -2.0, 3.0), (6.0, -2.0, 3.0), (6.0, 2.0, 4.5))  # slopes up to the north
LEVEL = ((1.0, 1.0, 3.0), (4.0, 1.0, 3.0), (4.0, 5.0, 3.0))
SKEWED = ((0.3, 0.1, 0.2), (2.9, 1.7, 0.9), (-0.4, 2.2, 3.1))


@pytest.mark.parametrize("triangle", [WALL, ROOF, LEVEL, SKEWED])
def test_every_edge_keeps_its_length_in_metres(triangle: tuple[Point, Point, Point]) -> None:
    uvs = face_uvs(*triangle)
    for i, j in combinations(range(3), 2):
        assert math.dist(uvs[i], uvs[j]) == pytest.approx(math.dist(triangle[i], triangle[j]))


def test_a_wall_runs_u_along_it_and_v_up_it() -> None:
    (_, v0), (u1, v1), (u2, v2) = face_uvs(*WALL)
    assert v1 == pytest.approx(v0)  # along the bottom edge: v is level
    assert u2 == pytest.approx(u1)  # up the end: u is constant
    assert v2 - v1 == pytest.approx(3.0)  # and v rises with height


def test_a_roof_runs_v_up_its_slope() -> None:
    (_, v0), (_, v1), (_, v2) = face_uvs(*ROOF)
    assert v1 == pytest.approx(v0)  # the eaves are level
    assert v2 - v1 == pytest.approx(math.hypot(4.0, 1.5))  # the slope's own length


def test_a_level_face_maps_east_and_north() -> None:
    assert face_uvs(*LEVEL) == [
        pytest.approx((1.0, 1.0)),
        pytest.approx((4.0, 1.0)),
        pytest.approx((4.0, 5.0)),
    ]


def test_v_rises_with_height_whichever_way_the_face_winds() -> None:
    a, b, c = WALL
    (_, v_bottom), (_, v_top), _ = face_uvs(a, c, b)  # wound the other way
    assert v_top - v_bottom == pytest.approx(3.0)


def test_coplanar_faces_share_the_mapping() -> None:
    a, b, c = WALL
    d = (2.0, -3.0, 3.5)
    first = dict(zip((a, b, c), face_uvs(a, b, c), strict=True))
    second = dict(zip((a, c, d), face_uvs(a, c, d), strict=True))
    assert second[a] == pytest.approx(first[a]) and second[c] == pytest.approx(first[c])


@pytest.mark.parametrize("triangle", [WALL, ROOF])
def test_coplanar_faces_wound_opposite_ways_share_the_mapping(
    triangle: tuple[Point, Point, Point],
) -> None:
    a, b, c = triangle
    d = (a[0] + c[0] - b[0], a[1] + c[1] - b[1], a[2] + c[2] - b[2])  # completes the quad
    first = dict(zip((a, b, c), face_uvs(a, b, c), strict=True))
    second = dict(zip((a, d, c), face_uvs(a, d, c), strict=True))  # the other winding
    assert second[a] == pytest.approx(first[a]) and second[c] == pytest.approx(first[c])


@pytest.mark.parametrize("turn_deg", [45, 135, 225, 315])
def test_a_slope_turned_diagonally_is_seamless(turn_deg: int) -> None:
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    rng = random.Random(turn_deg)
    for _ in range(200):  # gable slopes of many sizes and places, turned to face a diagonal
        length, run, rise = rng.uniform(3, 15), rng.uniform(1, 4), rng.uniform(0.3, 2)
        x0, y0, eaves = rng.uniform(-20, 20), rng.uniform(-20, 20), rng.uniform(2, 3)
        slope = [(0, 0, 0), (length, 0, 0), (length, run, rise), (0, run, rise)]
        a, b, top, d = ((x0 + x * c - y * s, y0 + x * s + y * c, eaves + z) for x, y, z in slope)
        first = dict(zip((a, b, top), face_uvs(a, b, top), strict=True))
        second = dict(zip((a, top, d), face_uvs(a, top, d), strict=True))
        assert second[a] == pytest.approx(first[a]) and second[top] == pytest.approx(first[top])


def test_a_degenerate_face_maps_without_failing() -> None:
    point = (1.0, 2.0, 3.0)
    assert face_uvs(point, point, point) == [(1.0, 2.0)] * 3
