"""Tests for button_nz.agent.proposal: Blender measurements to evaluator proposals."""

import pytest
from shapely import Polygon

from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.geo.crs import LocalFrame
from meshes import a_frame, box, hollow_house

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


def test_a_doorway_through_the_walls_is_feedback_not_a_tiny_footprint() -> None:
    with pytest.raises(DesignError, match="solid"):
        parse_measurements(measured_with(hollow_house(door=True)))


def test_a_terrace_beside_the_walls_is_not_their_floor() -> None:
    house = box(0, 0, 0.9, 8, 8, 4)
    terrace = box(8, 0, 0, 15.5, 8, 0.2)
    with pytest.raises(DesignError, match="lowest"):
        parse_measurements(measured_with(house + terrace))


def test_a_doorway_is_caught_without_a_floor_slab_too() -> None:
    """Walls standing on z_min, door gap to the ground: the floor section has the gap too."""
    with pytest.raises(DesignError, match="solid"):
        parse_measurements(measured_with(hollow_house(door=True, slab=False)))


def test_an_l_shaped_solid_house_is_fine() -> None:
    l_shape = box(0, 0, 0, 10, 4, 3) + box(0, 4, 0, 4, 10, 3)
    measured = parse_measurements(measured_with(l_shape))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area == pytest.approx(64.0)


def test_a_doorway_into_one_room_of_two_is_caught() -> None:
    """The closed east room fills in; the west room's front door must still be caught."""
    house = hollow_house(door=True, door_x=2.5) + box(5.9, 0.2, 0.2, 6.1, 9.8, 3)
    with pytest.raises(DesignError, match="solid"):
        parse_measurements(measured_with(house))


def test_a_u_shaped_house_with_a_wide_courtyard_is_fine() -> None:
    u_shape = box(0, 0, 0, 10, 3, 3) + box(0, 3, 0, 3, 8, 3) + box(7, 3, 0, 10, 8, 3)
    measured = parse_measurements(measured_with(u_shape))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area == pytest.approx(60.0)


def test_a_house_without_a_roof_is_feedback() -> None:
    roofless = [t for t in hollow_house(door=False) if min(p[2] for p in t) < 3.0]
    with pytest.raises(DesignError, match="roof"):
        parse_measurements(measured_with(roofless))


def test_an_opening_too_wide_to_bridge_is_still_caught() -> None:
    """A 3 m opening (garage door, slider) leaves the walls a thin strip of their hull."""
    wide = hollow_house(door=True, door_x=4.0, door_width=3.0)
    with pytest.raises(DesignError, match="solid"):
        parse_measurements(measured_with(wide))


def test_an_a_frame_is_a_closed_envelope() -> None:
    measured = parse_measurements(measured_with(a_frame(7.0, 9.0, 3.9)))
    assert measured.footprint is not None


def test_a_mesh_without_a_bottom_face_has_no_floor() -> None:
    """Walls and a roof but no bottom: the wall ring sections as full, yet nothing closes it."""
    closed = box(0, 0, 0, 8, 6, 3)
    no_bottom = closed[2:]  # box() lists the two bottom triangles first
    with pytest.raises(DesignError, match="lowest"):
        parse_measurements(measured_with(no_bottom))


def test_an_a_frame_is_measured_near_its_floor() -> None:
    """Its slopes narrow as they rise: a cut 1 m up would understate the floor."""
    measured = parse_measurements(measured_with(a_frame(10.0, 9.0, 3.9)))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area > 75.0  # the 0.5 m cut: about 78 m² of 90


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_coordinates_are_feedback(bad: float) -> None:
    broken = box(0, 0, 0, 8, 6, 3)
    broken[0] = [[bad, 0.0, 0.0], broken[0][1], broken[0][2]]
    with pytest.raises(DesignError, match="finite"):
        parse_measurements(measured_with(broken))


def test_a_step_below_the_wall_cut_is_not_mistaken_for_the_walls() -> None:
    """A raised house with a doorway and a solid front step: the step at 0.5 m must
    not stand in for the walls at 1 m."""
    raised = [[[x, y, z + 0.6] for x, y, z in tri] for tri in hollow_house(door=True)]
    step = box(4.5, -3, 0, 7.5, 0.2, 0.6)
    with pytest.raises(DesignError, match="lowest|solid"):  # the step is below the floor too
        parse_measurements(measured_with(raised + step))


def test_a_deck_at_floor_level_is_not_part_of_the_walls() -> None:
    house = box(0, 0, 0, 8, 6, 3)
    deck = box(8, 0, 0, 12, 6, 0.6)  # underside level with the floor
    measured = parse_measurements(measured_with(house + deck))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area == pytest.approx(48.0)


def test_an_a_frame_with_an_entry_platform_is_still_measured_near_its_floor() -> None:
    platform = box(0, -3, 0, 10, 0, 0.6)
    measured = parse_measurements(measured_with(a_frame(10.0, 9.0, 3.9) + platform))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area > 75.0


def _banded(triangles: list[list[list[float]]], z: float) -> list[list[list[float]]]:
    """``triangles`` with every edge crossing height ``z`` split there, as a
    subdivided or loop-cut mesh would be: no triangle crosses ``z`` any more."""
    out: list[list[list[float]]] = []
    for tri in triangles:
        below = [p for p in tri if p[2] < z]
        if not below or len(below) == 3:
            out.append(tri)
            continue
        out += _split(tri, z)
    return out


def _split(tri: list[list[float]], z: float) -> list[list[list[float]]]:
    def cross(a: list[float], b: list[float]) -> list[float]:
        a, b = sorted((a, b))  # the same point from both triangles sharing the edge
        t = (z - a[2]) / (b[2] - a[2])
        return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), z]

    lone = next(
        i
        for i in range(3)
        if (tri[i][2] < z) != (tri[(i + 1) % 3][2] < z)
        and (tri[i][2] < z) != (tri[(i + 2) % 3][2] < z)
    )
    a, b, c = tri[lone], tri[(lone + 1) % 3], tri[(lone + 2) % 3]
    ab, ac = cross(a, b), cross(a, c)
    return [[a, ab, ac], [ab, b, c], [ab, c, ac]]


def test_a_banded_a_frame_is_still_measured_near_its_floor() -> None:
    """Loop-cut at 0.75 m, no triangle crossing the 0.5 m cut reaches 1 m."""
    banded = _banded(a_frame(10.0, 9.0, 3.9), 0.75)
    measured = parse_measurements(measured_with(banded))
    assert measured.footprint is not None
    assert Polygon(measured.footprint).area > 75.0


def test_an_a_frame_with_a_deck_on_its_long_side_is_measured_near_its_floor() -> None:
    deck = box(10, 0, 0, 13, 9, 0.6)
    measured = parse_measurements(measured_with(a_frame(10.0, 9.0, 3.9) + deck))
    assert measured.footprint is not None
    assert 75.0 < Polygon(measured.footprint).area < 85.0  # the A-frame, not the deck


def test_a_screen_wall_joined_to_the_house_widens_its_outline() -> None:
    screen = [[[8.0, 3.0, 0.0], [14.0, 3.0, 0.0], [14.0, 3.0, 2.0]]]
    measured = parse_measurements(measured_with(box(0, 0, 0, 8, 6, 3) + screen))
    assert measured.parts == 1 and measured.outline is not None
    assert max(x for x, _ in measured.outline) == pytest.approx(14.0, abs=0.01)


def test_a_detached_screen_wall_is_a_separate_piece() -> None:
    screen = [[[10.0, 3.0, 0.0], [14.0, 3.0, 0.0], [14.0, 3.0, 2.0]]]
    with pytest.raises(DesignError, match="pieces"):
        to_proposal(parse_measurements(measured_with(box(0, 0, 0, 8, 6, 3) + screen)), FRAME, DATUM)
