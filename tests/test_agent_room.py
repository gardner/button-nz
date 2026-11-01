"""Tests for button_nz.agent.room: where a dwelling fits, as rectangles."""

import re

import numpy as np
from shapely import LineString, Point, Polygon, box

from button_nz.agent.room import (
    MIN_WIDTH_M,
    describe_room,
    largest_rectangles,
    rectangles_text,
    room_of,
)
from button_nz.evaluation import SiteContext
from button_nz.geo.terrain import TerrainGrid

TITLE = ((0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0), (0.0, 0.0))


def test_an_empty_title_has_room_inside_its_setback() -> None:
    room = room_of([TITLE], buildings=[], keep_clear=[])
    assert abs(room.area - 16 * 26) < 0.5  # 2 m in from every boundary, never less


def test_buildings_with_their_halo_and_kept_areas_are_taken_out() -> None:
    shed = ((4.0, 4.0), (8.0, 4.0), (8.0, 8.0), (4.0, 8.0), (4.0, 4.0))
    tree = ((12.0, 20.0), (16.0, 20.0), (16.0, 24.0), (12.0, 24.0), (12.0, 20.0))
    room = room_of([TITLE], buildings=[shed], keep_clear=[tree])
    assert not room.intersects(box(4.5, 4.5, 7.5, 7.5).buffer(1.9))  # shed and halo
    assert not room.intersects(box(12.5, 20.5, 15.5, 23.5))  # the tree


def test_the_largest_rectangle_in_open_room_is_the_room() -> None:
    (best,) = largest_rectangles(box(2, 2, 18, 28), angle_deg=0.0, count=1)
    assert abs(best.length_m - 26) <= 0.5 and abs(best.width_m - 16) <= 0.5
    assert best.polygon.within(box(2, 2, 18, 28).buffer(1e-6))


def test_a_kept_area_splits_the_room_into_the_two_largest_rectangles() -> None:
    room = box(2, 2, 18, 28).difference(box(2, 12, 18, 16))  # a band kept clear across it
    first, second = largest_rectangles(room, angle_deg=0.0, count=2)
    # Only cells wholly in the room count: up to half a metre less on each side.
    assert 15 * 11 <= first.polygon.area <= 16 * 12 and 15 * 9 <= second.polygon.area <= 16 * 10
    assert not first.polygon.intersects(second.polygon.buffer(-0.01))


def test_a_turned_title_gives_rectangles_square_to_it() -> None:
    turned = Polygon([(0, 0), (10, 10), (0, 20), (-10, 10)])  # a square at 45°
    (best,) = largest_rectangles(turned, angle_deg=45.0, count=1)
    assert best.polygon.area > 0.9 * turned.area


def test_a_rectangle_too_narrow_for_a_dwelling_isnt_offered() -> None:
    room = box(2, 2, 18, 28).union(box(18, 2, 18.2, 28))  # a 0.2 m strip beside the room
    found = largest_rectangles(room, angle_deg=0.0, count=2)
    assert all(r.width_m >= MIN_WIDTH_M for r in found)


def test_every_rectangle_lies_inside_the_room_even_off_the_grid() -> None:
    for room, angle in ((box(2, 2, 18.2, 28.1), 0.0), (box(2, 2, 18.2, 28.1), 17.0)):
        for rect in largest_rectangles(room, angle_deg=angle, count=2):
            assert rect.polygon.within(room), (angle, rect.polygon.bounds)


def test_a_halo_is_at_least_2_m_everywhere() -> None:
    house = ((8.0, 18.0), (14.0, 18.0), (14.0, 24.0), (8.0, 24.0), (8.0, 18.0))
    room = room_of([TITLE], buildings=[house], keep_clear=[])
    assert room.distance(Polygon(house)) >= 2.0 - 1e-9


def test_no_rectangle_crosses_a_line_between_two_sections_of_the_title() -> None:
    a = ((0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0), (0.0, 0.0))
    b = ((20.0, 0.0), (40.0, 0.0), (40.0, 30.0), (20.0, 30.0), (20.0, 0.0))
    room = room_of([a, b], buildings=[], keep_clear=[])
    # Only crossing a section line fails (s 42B): near one is the evaluator's
    # "unknown", not a lost 4 m strip, so the room reaches the line.
    assert room.area > 36 * 26 - 4  # the 40 x 30 m title inset 2 m, less the line itself
    for rect in largest_rectangles(room, angle_deg=0.0, count=2):
        assert not rect.polygon.intersects(LineString([(20, 0), (20, 30)]))


def test_a_long_narrow_strip_doesnt_hide_a_usable_block() -> None:
    strip = box(0, 0, 2.9, 35)  # 101 m², too narrow
    block = box(10, 0, 19, 10)  # 90 m²
    found = largest_rectangles(strip.union(block), angle_deg=0.0, count=2)
    assert found and found[0].width_m >= 8.5


def test_a_kept_corner_poking_into_a_cell_never_spoils_the_largest_rectangle() -> None:
    # A diamond kept area whose lowest vertex pokes 0.01 m into the open room
    # inside one grid cell, missing all of its corners.
    room = box(2, 2, 18, 28)
    diamond = Polygon([(10.1, 14.99), (12, 17), (10.1, 19), (8, 17)])
    found = largest_rectangles(room.difference(diamond), angle_deg=0.0, count=2)
    assert found, "the room is mostly open: something fits"
    for rect in found:
        assert rect.polygon.within(room.difference(diamond))
    assert found[0].polygon.area >= 16 * 12 - 16  # the open part below it, about 16 x 12.9


def test_printed_corners_lie_in_the_room_after_rounding() -> None:
    room = box(2.0024, 2.0024, 17.9976, 27.9976)  # a real setback's 2.4 mm of slack
    text = rectangles_text(largest_rectangles(room, angle_deg=0.0, count=1), lambda p: p)
    pairs = re.findall(r"\(([-\d.]+), ([-\d.]+)\)", text)
    corners = [(float(x), float(y)) for x, y in pairs]
    assert corners and all(room.covers(Point(x, y)) for x, y in corners)


def test_a_printed_size_is_never_larger_than_its_printed_corners() -> None:
    room = box(2.0024, 2.0024, 8.8, 27.9976)  # 6.80 m wide: the grid fits 6.75
    text = rectangles_text(largest_rectangles(room, angle_deg=0.0, count=1), lambda p: p)
    size = re.search(r"1: ([\d.]+) x ([\d.]+) m", text)
    assert size is not None
    pairs = re.findall(r"\(([-\d.]+), ([-\d.]+)\)", text)
    xs, ys = [float(x) for x, _ in pairs], [float(y) for _, y in pairs]
    spans = sorted((max(xs) - min(xs), max(ys) - min(ys)), reverse=True)
    assert float(size[1]) <= spans[0] and float(size[2]) <= spans[1]


def test_a_room_with_no_square_rectangle_says_only_that() -> None:
    sliver = ((0.0, 0.0), (40.0, 0.0), (40.0, 6.5), (0.0, 6.5), (0.0, 0.0))  # 2.5 m once inset
    site = SiteContext(parcels=(sliver,), terrain=_terrain())
    text = describe_room(site, lambda p: p)
    assert "no rectangle at least 3 m wide fits in it square to the title" in text
    assert "none left" not in text


def _terrain() -> TerrainGrid:
    flat = np.full((10, 40), 100.0)
    return TerrainGrid((0.0, 0.0, 40.0, 10.0), 1.0, flat, np.zeros_like(flat), ("synthetic",))
