"""Tests for button_nz.agent.room: where a dwelling fits, as rectangles."""

from shapely import Polygon, box

from button_nz.agent.room import MIN_WIDTH_M, largest_rectangles, room_of

TITLE = ((0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0), (0.0, 0.0))


def test_an_empty_title_has_room_inside_its_setback() -> None:
    room = room_of([TITLE], buildings=[], keep_clear=[])
    assert abs(room.area - 16 * 26) < 1e-6  # 2 m in from every boundary


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
    assert abs(first.polygon.area - 16 * 12) <= 8 and abs(second.polygon.area - 16 * 10) <= 8
    assert not first.polygon.intersects(second.polygon.buffer(-0.01))


def test_a_turned_title_gives_rectangles_square_to_it() -> None:
    turned = Polygon([(0, 0), (10, 10), (0, 20), (-10, 10)])  # a square at 45°
    (best,) = largest_rectangles(turned, angle_deg=45.0, count=1)
    assert best.polygon.area > 0.9 * turned.area


def test_what_the_lidar_shows_standing_is_kept_clear_with_room_round_it() -> None:
    house = box(8, 18, 14, 24)  # unlisted, but standing over 2 m on the LiDAR
    room = room_of([TITLE], buildings=[], keep_clear=[], standing=[house])
    assert room.distance(house) >= 1.99  # 2 m, less the buffer's rounding at corners


def test_a_rectangle_too_narrow_for_a_dwelling_isnt_offered() -> None:
    room = box(2, 2, 18, 28).union(box(18, 2, 18.2, 28))  # a 0.2 m strip beside the room
    found = largest_rectangles(room, angle_deg=0.0, count=2)
    assert all(r.width_m >= MIN_WIDTH_M for r in found)
