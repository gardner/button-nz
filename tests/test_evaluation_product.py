"""Tests for the product_footprint check: a placed prefab's walls must be its
published outside footprint."""

import pytest
from shapely import Polygon
from shapely.affinity import rotate

from button_nz.evaluation import Check, Footprint, Status, evaluate
from button_nz.geo.geometry import Ring
from test_evaluation import proposal, rect, site

VISTA = Footprint("AirHome Vista", length_m=12.2, width_m=4.0)


def turned(ring: Ring, degrees: float) -> Ring:
    shape = rotate(Polygon(ring), degrees, origin="centroid")
    return tuple((float(x), float(y)) for x, y, *_ in shape.exterior.coords)


def product_check(footprint: Ring, product: Footprint = VISTA) -> Check:
    report = evaluate(proposal(footprint=footprint, floor_area_m2=44.0), site(), product)
    return next(c for c in report.checks if c.name == "product_footprint")


def test_walls_that_are_the_product_pass() -> None:
    check = product_check(rect(2, 4, 14.2, 8))
    assert check.status is Status.PASS
    assert check.measured["length_m"] == pytest.approx(12.2)
    assert check.measured["width_m"] == pytest.approx(4.0)
    assert "AirHome Vista" in check.rule and "12.2 × 4 m" in check.rule


@pytest.mark.parametrize("degrees", [90.0, 33.0])
def test_the_product_may_turn_any_way(degrees: float) -> None:
    assert product_check(turned(rect(2, 4, 14.2, 8), degrees)).status is Status.PASS


def test_walls_within_a_tenth_of_a_metre_pass() -> None:
    assert product_check(rect(2, 4, 14.28, 7.93)).status is Status.PASS


def test_walls_longer_than_the_product_fail_with_the_measured_sides() -> None:
    check = product_check(rect(2, 4, 15.0, 8))
    assert check.status is Status.FAIL
    assert "13.0 × 4.0 m" in check.detail and "12.2 × 4 m" in check.detail


def test_walls_that_are_not_a_rectangle_fail() -> None:
    notched: Ring = ((2, 4), (14.2, 4), (14.2, 8), (8, 8), (8, 6), (2, 6), (2, 4))
    check = product_check(notched)
    assert check.status is Status.FAIL
    assert "not a rectangle" in check.detail
    assert check.measured["off_rectangle_m"] == pytest.approx(2.0)


def test_without_a_product_there_is_no_product_check() -> None:
    report = evaluate(proposal(), site())
    assert "product_footprint" not in {c.name for c in report.checks}


def test_a_product_that_fits_the_exemption_has_its_other_checks_run_too() -> None:
    report = evaluate(proposal(footprint=rect(2, 4, 14.2, 8)), site(), VISTA)
    names = [c.name for c in report.checks]
    assert names[0] == "product_footprint"
    assert "title_boundary_setback" in names and "floor_level" in names
