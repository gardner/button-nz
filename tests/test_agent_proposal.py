"""Tests for button_nz.agent.proposal: Blender measurements to evaluator proposals."""

import pytest
from shapely import Polygon

from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.geo.crs import LocalFrame
from meshes import box

FRAME = LocalFrame(origin=(1505948.0, 5336800.0))
DATUM = 189.25


def measured(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "error": None,
        "triangles": box(-3.0, -2.5, 0.6, 3.0, 2.5, 4.2),  # 6 m x 5 m, 3.6 m tall
        "floor_area_m2": 26.0,
        "storeys": 1,
    }
    return raw | overrides


def measured_with(triangles: object) -> dict[str, object]:
    return measured(triangles=triangles)


def test_measurements_become_an_nztm_proposal() -> None:
    proposal = to_proposal(parse_measurements(measured()), FRAME, DATUM)
    xs = [x for x, _ in proposal.footprint]
    ys = [y for _, y in proposal.footprint]
    assert (min(xs), min(ys)) == pytest.approx((1505945.0, 5336797.5))
    assert (max(xs), max(ys)) == pytest.approx((1505951.0, 5336802.5))
    assert len(proposal.footprint) == 5  # triangles merged into one rectangle
    assert proposal.outline is not None and Polygon(proposal.outline).area == pytest.approx(30.0)
    assert proposal.floor_level_m == pytest.approx(189.85)
    assert proposal.height_above_floor_m == pytest.approx(3.6)
    assert proposal.floor_area_m2 == 26.0
    assert proposal.storeys == 1


def test_unset_properties_stay_unknown() -> None:
    raw = measured(floor_area_m2=None, storeys=None)
    proposal = to_proposal(parse_measurements(raw), FRAME, DATUM)
    assert proposal.floor_area_m2 is None
    assert proposal.storeys is None


def test_a_script_error_is_feedback_for_the_model() -> None:
    raw = measured(error="NameError: name 'bpyy' is not defined", triangles=None)
    with pytest.raises(DesignError, match="NameError"):
        to_proposal(parse_measurements(raw), FRAME, DATUM)


def test_a_missing_dwelling_is_feedback_for_the_model() -> None:
    with pytest.raises(DesignError, match="Dwelling"):
        to_proposal(parse_measurements(measured(triangles=None)), FRAME, DATUM)


def test_a_split_footprint_is_feedback_for_the_model() -> None:
    with pytest.raises(DesignError, match="one connected"):
        apart = box(0, 0, 0, 1, 1, 3) + box(5, 5, 0, 6, 6, 3)
        to_proposal(parse_measurements(measured(triangles=apart)), FRAME, DATUM)


@pytest.mark.parametrize(
    "bad",
    [{"storeys": 1.5}, {"storeys": "one"}, {"floor_area_m2": "big"}, {"floor_area_m2": [26.0]}],
)
def test_malformed_dwelling_properties_are_feedback(bad: dict[str, object]) -> None:
    with pytest.raises(DesignError, match="Dwelling"):
        to_proposal(parse_measurements(measured(**bad)), FRAME, DATUM)


def test_eaves_widen_the_outline_but_not_the_wall_footprint() -> None:
    """Floor area is measured inside the external walls (MBIE guidance p. 26)."""
    walls, eaves = box(0, 0, 0, 8, 8, 3), box(-1, -1, 3, 9, 9, 3.3)
    proposal = to_proposal(parse_measurements(measured(triangles=walls + eaves)), FRAME, DATUM)
    assert Polygon(proposal.footprint).area == pytest.approx(64.0)
    assert proposal.outline is not None and Polygon(proposal.outline).area == pytest.approx(100.0)
    assert proposal.height_above_floor_m == pytest.approx(3.3)


def test_geometry_below_the_floor_is_feedback() -> None:
    """Piles under a raised floor would make the floor look lower than it is."""
    floor = box(0, 0, 0.9, 8, 8, 4.0)
    piles = [
        t
        for x, y in ((0, 0), (7.7, 0), (0, 7.7), (7.7, 7.7))
        for t in box(x, y, 0, x + 0.3, y + 0.3, 0.9)
    ]
    with pytest.raises(DesignError, match="lowest"):
        parse_measurements(measured(triangles=floor + piles))


def test_an_open_mesh_is_feedback() -> None:
    sheet = [[[0.0, 0.0, 0.0], [4.0, 0.0, 2.0], [4.0, 4.0, 2.0]]]
    with pytest.raises(DesignError, match="closed"):
        parse_measurements(measured(triangles=sheet))


def test_posts_and_balustrades_do_not_split_the_walls() -> None:
    house = box(0, 0, 0, 8, 6, 3)
    veranda = box(0, 6, 2.7, 8, 8.5, 2.9)
    posts = box(0.1, 8.2, 0, 0.3, 8.4, 2.7) + box(7.7, 8.2, 0, 7.9, 8.4, 2.7)
    measured = parse_measurements(measured_with(house + veranda + posts))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area == pytest.approx(48.0)


def test_two_substantial_wall_outlines_are_feedback_with_their_sizes() -> None:
    joined = box(0, 0, 0, 4, 4, 3) + box(6, 0, 0, 10, 4, 3) + box(0, 0, 3, 10, 4, 3.2)
    with pytest.raises(DesignError, match=r"16 m², 16 m²"):
        parse_measurements(measured_with(joined))


def _hollow_house(door: bool) -> list[list[list[float]]]:
    """A 12 m x 10 m house the usual bpy way: slab, four 0.2 m walls, roof."""
    slab = box(0, 0, 0, 12, 10, 0.2)
    north, east, west = (
        box(0, 9.8, 0.2, 12, 10, 3),
        box(11.8, 0, 0.2, 12, 10, 3),
        box(0, 0, 0.2, 0.2, 10, 3),
    )
    south = (
        box(0.2, 0, 0.2, 5.5, 0.2, 3) + box(6.5, 0, 0.2, 11.8, 0.2, 3)
        if door
        else box(0.2, 0, 0.2, 11.8, 0.2, 3)
    )
    lintel = box(5.5, 0, 2.1, 6.5, 0.2, 3) if door else []
    roof = box(0, 0, 3, 12, 10, 3.2)
    return slab + north + east + west + south + lintel + roof


def test_a_doorway_through_the_walls_is_feedback_not_a_tiny_footprint() -> None:
    with pytest.raises(DesignError, match="solid"):
        parse_measurements(measured_with(_hollow_house(door=True)))


def test_a_terrace_beside_the_walls_is_not_their_floor() -> None:
    house = box(0, 0, 0.9, 8, 8, 4)
    terrace = box(8, 0, 0, 15.5, 8, 0.2)
    with pytest.raises(DesignError, match="lowest"):
        parse_measurements(measured_with(house + terrace))
