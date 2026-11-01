"""Tests for open courtyards in button_nz.agent.proposal: a courtyard open to the
sky is not floor, so it is cut out of the wall footprint; a roofed room is."""

import json
from pathlib import Path

import pytest
from shapely import Polygon

from button_nz.agent.proposal import DesignError, Measurements, parse_measurements, to_proposal
from button_nz.geo.crs import LocalFrame
from button_nz.sites.design_map import walls_and_outline
from meshes import Triangle, a_frame, box, hollow_house
from test_agent_proposal import measured_with

FRAME = LocalFrame(origin=(1505948.0, 5336800.0))


def _courtyard_house(size: float, court: float, overlap: bool = False) -> list[Triangle]:
    """A ``size`` m square house the usual bpy way: four wing boxes, 3 m tall,
    around an open ``court`` m square courtyard in its middle. With ``overlap``
    the east and west wings run the full depth, through the others' ends."""
    a, b = (size - court) / 2, (size + court) / 2
    south, north = box(0, 0, 0, size, a, 3), box(0, b, 0, size, size, 3)
    if overlap:
        return south + north + box(0, 0, 0, a, size, 3) + box(b, 0, 0, size, size, 3)
    return south + north + box(0, a, 0, a, b, 3) + box(b, a, 0, size, b, 3)


def _walls(measured: Measurements) -> Polygon:
    walls = measured.walls()
    assert walls is not None
    return walls


@pytest.mark.parametrize("overlap", [False, True])
def test_a_large_open_courtyard_is_cut_out_of_the_footprint(overlap: bool) -> None:
    """16 m² of 144 (11 %): it used to be refused as having no floor under it."""
    measured = parse_measurements(measured_with(_courtyard_house(12, 4, overlap)))
    assert Polygon(measured.footprint or ()).area == pytest.approx(144.0)
    assert [Polygon(c).area for c in measured.courtyards] == pytest.approx([16.0])
    assert _walls(measured).area == pytest.approx(128.0)


def test_a_small_open_courtyard_is_not_counted_as_floor() -> None:
    """16 m² of 196 (8 %): it used to count as footprint."""
    measured = parse_measurements(measured_with(_courtyard_house(14, 4)))
    assert _walls(measured).area == pytest.approx(180.0)


def test_eaves_over_a_courtyard_shrink_it_to_what_is_open() -> None:
    """The stricter reading: 0.5 m eaves overhang it, so 3 m x 3 m of it is open."""
    roof = box(-0.5, -0.5, 3, 12.5, 4.5, 3.2) + box(-0.5, 7.5, 3, 12.5, 12.5, 3.2)
    roof += box(-0.5, 4.5, 3, 4.5, 7.5, 3.2) + box(7.5, 4.5, 3, 12.5, 7.5, 3.2)
    measured = parse_measurements(measured_with(_courtyard_house(12, 4) + roof))
    assert _walls(measured).area == pytest.approx(135.0)


def _skylit(rails: bool) -> list[Triangle]:
    """Two hollow rooms; an unglazed 2.5 m x 2.5 m opening in the roof over the
    west one, and with ``rails`` a balustrade round it, 1.1 m high."""
    house = [t for t in hollow_house(door=False) if min(p[2] for p in t) < 3.0]
    house += box(5.9, 0.2, 0.2, 6.1, 9.8, 3)  # the wall between the rooms
    roof = box(0, 0, 3, 12, 3.5, 3.2) + box(0, 6, 3, 12, 10, 3.2)
    roof += box(0, 3.5, 3, 1.5, 6, 3.2) + box(4, 3.5, 3, 12, 6, 3.2)
    if not rails:
        return house + roof
    ring = box(1.5, 3.5, 0.2, 4, 3.55, 1.1) + box(1.5, 5.95, 0.2, 4, 6, 1.1)
    ring += box(1.5, 3.55, 0.2, 1.55, 5.95, 1.1) + box(3.95, 3.55, 0.2, 4, 5.95, 1.1)
    return house + roof + ring


@pytest.mark.parametrize("rails", [False, True])
def test_an_opening_in_a_rooms_roof_is_no_courtyard(rails: bool) -> None:
    """The room is mostly roofed, so it is floor; a balustrade round the opening
    encloses it at the wall cut, but no wall does 2 m up."""
    measured = parse_measurements(measured_with(_skylit(rails)))
    assert measured.courtyards == ()
    assert _walls(measured).area == pytest.approx(120.0)


def _alcove_house(alcove_to: float) -> list[Triangle]:
    """A 14 m square courtyard house, its 4 m courtyard (5-9 m) opening east into
    a roofed alcove, floored, that reaches ``alcove_to`` into the east wing."""
    rest = [t for t in _courtyard_house(14, 4) if min(p[0] for p in t) < 9]  # no east wing
    east = box(alcove_to, 5, 0, 14, 9, 3)
    alcove = box(9, 5, 0, alcove_to, 9, 0.2) + box(9, 5, 2.8, alcove_to, 9, 3)
    return rest + box(9, 0, 0, 14, 5, 3) + box(9, 9, 0, 14, 14, 3) + east + alcove


def test_a_roofed_alcove_open_to_a_courtyard_stays_floor() -> None:
    """One face at the wall cut, mostly open: only its open part is the courtyard."""
    measured = parse_measurements(measured_with(_alcove_house(11)))
    assert [Polygon(c).area for c in measured.courtyards] == pytest.approx([16.0])
    assert _walls(measured).area == pytest.approx(180.0)


def test_a_courtyard_joined_to_a_larger_roofed_room_is_floor() -> None:
    """Mostly roofed (18 of 34 m²), the face is a room: the stricter reading."""
    measured = parse_measurements(measured_with(_alcove_house(13.5)))
    assert measured.courtyards == ()
    assert _walls(measured).area == pytest.approx(196.0)


def test_a_roofed_atrium_is_floor_not_a_courtyard() -> None:
    glazed = box(4, 4, 2.8, 8, 8, 3)  # a roof over the court, a floor in it: a room
    paved = box(4, 4, 0, 8, 8, 0.2)
    measured = parse_measurements(measured_with(_courtyard_house(12, 4) + glazed + paved))
    assert measured.courtyards == ()
    assert _walls(measured).area == pytest.approx(144.0)


def _benched(width: float) -> list[Triangle]:
    """An 11 m square courtyard house, its 5 m courtyard (3-8 m) with a bench
    ``width`` wide and 0.9 m high round it: the courtyard's sides step in below
    the wall cut, as sloping sides would."""
    a, b = 3 + width, 8 - width
    bench = box(3, 3, 0, 8, a, 0.9) + box(3, b, 0, 8, 8, 0.9)
    bench += box(3, a, 0, a, b, 0.9) + box(b, a, 0, 8, b, 0.9)
    return _courtyard_house(11, 5) + bench


def test_a_courtyard_is_measured_no_bigger_than_it_is_near_the_floor() -> None:
    """5 m x 5 m open at the wall cut, but 4.4 m x 4.4 m at the floor."""
    measured = parse_measurements(measured_with(_benched(0.3)))
    assert [Polygon(c).area for c in measured.courtyards] == pytest.approx([4.4**2])
    assert _walls(measured).area == pytest.approx(121 - 4.4**2)


def test_open_sky_over_more_than_a_tenth_of_the_floor_is_still_no_roof() -> None:
    """A 1 m bench: 16 m² of floor under open sky, outside the 3 m x 3 m courtyard."""
    with pytest.raises(DesignError, match="no roof over its walls"):
        parse_measurements(measured_with(_benched(1.0)))


def test_a_courtyard_is_carried_into_the_proposal_in_nztm() -> None:
    measured = parse_measurements(measured_with(_courtyard_house(12, 4)))
    proposal = to_proposal(measured, FRAME, 100.0)
    assert len(proposal.courtyards) == 1
    court = Polygon(proposal.courtyards[0])
    assert court.area == pytest.approx(16.0)
    assert court.bounds == pytest.approx((1505952.0, 5336804.0, 1505956.0, 5336808.0))


def test_walls_with_no_roof_are_still_feedback_not_a_courtyard() -> None:
    """A roofless shell would be thin walls round a huge courtyard: still no roof."""
    roofless = [t for t in hollow_house(door=False) if min(p[2] for p in t) < 3.0]
    with pytest.raises(DesignError, match="roof"):
        parse_measurements(measured_with(roofless))


def test_a_deck_inside_its_balustrade_is_not_a_courtyard() -> None:
    """Rails 1.1 m high close the deck at the wall cut, but it is no courtyard: the
    walls must still enclose it 2 m up. So it is a roofless room, as before."""
    house, deck = box(0, 0, 0, 8, 6, 3), box(8, 0, 0, 11, 6, 0.2)
    rails = box(8, 0, 0.2, 11, 0.05, 1.1) + box(8, 5.95, 0.2, 11, 6, 1.1)
    rails += box(10.95, 0, 0.2, 11, 6, 1.1)
    with pytest.raises(DesignError, match="no roof over its walls"):
        parse_measurements(measured_with(house + deck + rails))


def test_a_courtyard_over_half_the_plan_is_feedback() -> None:
    with pytest.raises(DesignError, match="roof"):
        parse_measurements(measured_with(_courtyard_house(12, 9)))


# Plans with no open courtyard measure exactly as before: (mesh, wall footprint m²).
ORDINARY: dict[str, tuple[list[Triangle], float]] = {
    "box": (box(-3.0, -2.5, 0.6, 3.0, 2.5, 4.2), 30.0),
    "eaves": (box(0, 0, 0, 8, 8, 3) + box(-1, -1, 3, 9, 9, 3.3), 64.0),
    "l_shape": (box(0, 0, 0, 10, 4, 3) + box(0, 4, 0, 4, 10, 3), 64.0),
    "u_shape": (
        box(0, 0, 0, 10, 3, 3) + box(0, 3, 0, 3, 8, 3) + box(7, 3, 0, 10, 8, 3),
        60.0,
    ),
    "hollow_room": (hollow_house(door=False), 120.0),
    "two_hollow_rooms": (hollow_house(door=False) + box(5.9, 0.2, 0.2, 6.1, 9.8, 3), 120.0),
    "a_frame": (a_frame(7.0, 9.0, 3.9), 54.923077),  # measured near its floor
}


@pytest.mark.parametrize("name", ORDINARY)
def test_plans_without_an_open_courtyard_have_none(name: str) -> None:
    mesh, area = ORDINARY[name]
    measured = parse_measurements(measured_with(mesh))
    assert measured.courtyards == ()
    assert to_proposal(measured, FRAME, 100.0).courtyards == ()
    assert _walls(measured).area == pytest.approx(area)


def test_without_triangles_there_are_no_walls() -> None:
    assert parse_measurements({"error": "boom", "triangles": None}).walls() is None


def test_the_design_map_draws_the_courtyard_as_a_hole(tmp_path: Path) -> None:
    raw = measured_with(_courtyard_house(12, 4))
    (tmp_path / "measurements.json").write_text(json.dumps(raw), encoding="utf-8")
    scene = {"frame": {"origin_nztm": list(FRAME.origin)}}
    (tmp_path / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
    walls, outline = walls_and_outline(tmp_path)
    assert walls.area == pytest.approx(128.0)
    assert len(walls.interiors) == 1
    assert outline.area == pytest.approx(144.0)  # where it comes: the outer outline
