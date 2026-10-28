"""Tests for button_nz.agent.proposal: Blender measurements to evaluator proposals."""

import pytest

from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.geo.crs import LocalFrame

FRAME = LocalFrame(origin=(1505948.0, 5336800.0))
DATUM = 189.25


def measured(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "error": None,
        # Two faces of a 6 m x 5 m floor, plus a wall seen edge-on (zero area).
        "faces_xy": [
            [[-3.0, -2.5], [0.0, -2.5], [0.0, 2.5], [-3.0, 2.5]],
            [[0.0, -2.5], [3.0, -2.5], [3.0, 2.5], [0.0, 2.5]],
            [[-3.0, -2.5], [3.0, -2.5], [3.0, -2.5], [-3.0, -2.5]],
        ],
        "z_min": 0.6,
        "z_max": 4.2,
        "floor_area_m2": 26.0,
        "storeys": 1,
    }
    return raw | overrides


def test_measurements_become_an_nztm_proposal() -> None:
    proposal = to_proposal(parse_measurements(measured()), FRAME, DATUM)
    xs = [x for x, _ in proposal.footprint]
    ys = [y for _, y in proposal.footprint]
    assert (min(xs), min(ys)) == pytest.approx((1505945.0, 5336797.5))
    assert (max(xs), max(ys)) == pytest.approx((1505951.0, 5336802.5))
    assert len(proposal.footprint) == 5  # faces merged into one rectangle
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
    raw = measured(error="NameError: name 'bpyy' is not defined", faces_xy=None)
    with pytest.raises(DesignError, match="NameError"):
        to_proposal(parse_measurements(raw), FRAME, DATUM)


def test_a_missing_dwelling_is_feedback_for_the_model() -> None:
    with pytest.raises(DesignError, match="Dwelling"):
        to_proposal(parse_measurements(measured(faces_xy=None)), FRAME, DATUM)


def test_a_split_footprint_is_feedback_for_the_model() -> None:
    with pytest.raises(DesignError, match="one connected"):
        apart = [[[0, 0], [1, 0], [1, 1], [0, 1]], [[5, 5], [6, 5], [6, 6], [5, 6]]]
        to_proposal(parse_measurements(measured(faces_xy=apart)), FRAME, DATUM)


@pytest.mark.parametrize(
    "bad",
    [{"storeys": 1.5}, {"storeys": "one"}, {"floor_area_m2": "big"}, {"floor_area_m2": [26.0]}],
)
def test_malformed_dwelling_properties_are_feedback(bad: dict[str, object]) -> None:
    with pytest.raises(DesignError, match="Dwelling"):
        to_proposal(parse_measurements(measured(**bad)), FRAME, DATUM)
