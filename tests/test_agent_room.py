"""Tests for button_nz.agent.room: where a dwelling fits, as rectangles."""

from shapely import LineString, Polygon, box

from button_nz.agent.room import MIN_WIDTH_M, largest_rectangles, room_of

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
    house = box(8, 18, 14, 24)
    room = room_of([TITLE], buildings=[], keep_clear=[], standing=[house])
    assert room.distance(house) >= 2.0 - 1e-9


def test_no_rectangle_crosses_a_line_between_two_sections_of_the_title() -> None:
    a = ((0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0), (0.0, 0.0))
    b = ((20.0, 0.0), (40.0, 0.0), (40.0, 30.0), (20.0, 30.0), (20.0, 0.0))
    room = room_of([a, b], buildings=[], keep_clear=[])
    assert room.distance(LineString([(20, 0), (20, 30)])) >= 2.0 - 1e-9
    for rect in largest_rectangles(room, angle_deg=0.0, count=2):
        assert not rect.polygon.intersects(LineString([(20, 0), (20, 30)]))


def test_a_long_narrow_strip_doesnt_hide_a_usable_block() -> None:
    strip = box(0, 0, 2.9, 35)  # 101 m², too narrow
    block = box(10, 0, 19, 10)  # 90 m²
    found = largest_rectangles(strip.union(block), angle_deg=0.0, count=2)
    assert found and found[0].width_m >= 8.5
