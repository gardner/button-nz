"""Tests for open courtyards in button_nz.evaluation: the floor area excludes
them; everything measured from the outer walls or outline is as without one."""

import pytest

from button_nz.evaluation import Footprint, InvalidProposal, Status, evaluate
from test_evaluation import check, proposal, rect, site

HOUSE = rect(3, 3, 12, 12)  # 9 m x 9 m: 81 m², 36 m round
COURT = rect(6, 6, 9, 9)  # 3 m x 3 m open courtyard: 9 m²


def test_an_open_courtyard_is_not_floor_area() -> None:
    """Filled, the 81 m² footprint needs a stated area; less its courtyard it is 72."""
    filled = check(proposal(footprint=HOUSE, floor_area_m2=None), "floor_area")
    assert filled.status is Status.UNKNOWN
    result = check(proposal(footprint=HOUSE, courtyards=(COURT,), floor_area_m2=None), "floor_area")
    assert result.measured["footprint_area_m2"] == pytest.approx(72.0)
    assert result.measured["courtyard_area_m2"] == pytest.approx(9.0)


def test_the_walls_round_a_courtyard_are_not_credited_with_thickness() -> None:
    """The stricter reading: thin screens round a yard mustn't lower the least inside."""
    result = check(proposal(footprint=HOUSE, courtyards=(COURT,)), "floor_area")
    assert result.measured["least_internal_area_m2"] == pytest.approx(72.0 - 36 * 0.6)


def test_a_courtyard_can_bring_a_footprint_under_70() -> None:
    big = rect(3, 3, 13, 13)  # 100 m²: even 0.6 m walls leave 76 inside
    assert check(proposal(footprint=big), "floor_area").status is Status.FAIL
    court = rect(5, 5, 11, 11)  # 36 m² open: 64 m² of footprint
    assert check(proposal(footprint=big, courtyards=(court,)), "floor_area").status is Status.PASS


def test_without_a_courtyard_floor_area_reports_no_courtyard() -> None:
    assert "courtyard_area_m2" not in check(proposal(footprint=HOUSE), "floor_area").measured


@pytest.mark.parametrize(
    "name",
    [
        "within_site",
        "title_boundary_setback",
        "section_boundary_setback",
        "building_separation",
        "floor_level",  # the ground in the courtyard still counts: the stricter reading
        "preservation_areas",
    ],
)
def test_checks_of_the_outer_walls_and_outline_are_unchanged(name: str) -> None:
    context = site(preservation_areas=(rect(7, 7, 9, 9),))  # inside the courtyard
    with_court = check(proposal(footprint=HOUSE, courtyards=(COURT,)), name, context)
    without = check(proposal(footprint=HOUSE), name, context)
    assert (with_court.status, dict(with_court.measured)) == (
        without.status,
        dict(without.measured),
    )


@pytest.mark.parametrize("court", [rect(10, 6, 14, 10), rect(20, 20, 22, 22), rect(6, 6, 6, 9)])
def test_a_courtyard_must_lie_inside_the_walls(court: tuple[tuple[float, float], ...]) -> None:
    with pytest.raises(InvalidProposal, match="courtyard"):
        evaluate(proposal(footprint=HOUSE, courtyards=(court,)), site())


def test_a_product_has_no_courtyard() -> None:
    square = Footprint("Square", length_m=10.0, width_m=10.0)
    report = evaluate(proposal(footprint=HOUSE, courtyards=(COURT,)), site(), square)
    result = next(c for c in report.checks if c.name == "product_footprint")
    assert result.status is Status.FAIL
