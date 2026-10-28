"""Tests for button_nz.evaluation: deterministic verdicts with known answers."""

import dataclasses

import numpy as np
import pytest

from button_nz.evaluation import Check, InvalidProposal, Proposal, SiteContext, Status, evaluate
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid


def rect(x0: float, y0: float, x1: float, y1: float) -> Ring:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))


# One title, two 20 m x 20 m sections side by side; the section line is x = 20.
PARCELS = (rect(0, 0, 20, 20), rect(20, 0, 40, 20))
GOOD = rect(5, 5, 13, 11)  # 8 m x 6 m, well inside section A


def terrain(ndsm_cells: tuple[tuple[int, int], ...] = ()) -> TerrainGrid:
    """1 m cells over (-5, -5)-(45, 25). Ground is 100 m, rising 0.02 m per metre east."""
    xs = np.arange(-5, 45, dtype=np.float64) + 0.5
    dem = np.tile(100.0 + 0.02 * xs, (30, 1)).astype(np.float64)
    ndsm = np.zeros_like(dem)
    for row, col in ndsm_cells:
        ndsm[row, col] = 5.0
    return TerrainGrid((-5.0, -5.0, 45.0, 25.0), 1.0, dem, ndsm, ("synthetic",))


def site(**overrides: object) -> SiteContext:
    base = SiteContext(parcels=PARCELS, terrain=terrain())
    return dataclasses.replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def proposal(**overrides: object) -> Proposal:
    base = Proposal(
        footprint=GOOD,
        floor_level_m=100.5,
        height_above_floor_m=3.8,
        floor_area_m2=42.0,
        storeys=1,
    )
    return dataclasses.replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def check(report_proposal: Proposal, name: str, context: SiteContext | None = None) -> Check:
    report = evaluate(report_proposal, context or site())
    return next(c for c in report.checks if c.name == name)


def test_a_good_placement_passes_every_measured_check() -> None:
    report = evaluate(
        proposal(),
        site(confirmed_buildings=(rect(30, 5, 36, 12),), buildings_confirmed=True),
    )
    statuses = {c.name: c.status for c in report.checks}
    assert statuses == {
        "within_site": Status.PASS,
        "title_boundary_setback": Status.PASS,
        "section_boundary_setback": Status.PASS,
        "building_separation": Status.PASS,
        "floor_area": Status.PASS,
        "single_storey": Status.PASS,
        "height": Status.PASS,
        "floor_level": Status.PASS,
        "preservation_areas": Status.PASS,
    }
    assert report.status is Status.PASS


def test_a_footprint_over_the_title_boundary_fails() -> None:
    result = check(proposal(footprint=rect(35, 5, 43, 11)), "within_site")
    assert result.status is Status.FAIL
    assert result.measured["area_outside_m2"] == pytest.approx(18.0)


def test_title_setback_is_measured_and_fails_under_2_m() -> None:
    result = check(proposal(footprint=rect(1.5, 5, 9.5, 11)), "title_boundary_setback")
    assert result.status is Status.FAIL
    assert result.measured["distance_m"] == pytest.approx(1.5)
    assert result.measured["required_m"] == 2.0


def test_a_section_line_within_2_m_is_unknown_not_failed() -> None:
    result = check(proposal(footprint=rect(11, 5, 19, 11)), "section_boundary_setback")
    assert result.status is Status.UNKNOWN
    assert result.measured["distance_m"] == pytest.approx(1.0)


def test_building_over_a_section_line_fails() -> None:
    """s 42B: not over a boundary between allotments, even on one record of title."""
    straddle = proposal(footprint=rect(16, 5, 24, 11))
    assert check(straddle, "within_site").status is Status.PASS
    result = check(straddle, "section_boundary_setback")
    assert result.status is Status.FAIL
    assert result.measured["distance_m"] == 0.0
    assert "42B" in result.rule


def test_a_footprint_touching_a_section_line_is_not_over_it() -> None:
    result = check(proposal(footprint=rect(12, 5, 20, 11)), "section_boundary_setback")
    assert result.status is Status.UNKNOWN
    assert result.measured["distance_m"] == 0.0


def test_building_separation_is_unknown_without_confirmed_buildings() -> None:
    result = check(proposal(), "building_separation")
    assert result.status is Status.UNKNOWN


def test_building_separation_fails_under_2_m() -> None:
    near = site(confirmed_buildings=(rect(14, 5, 18, 11),))
    result = check(proposal(), "building_separation", near)
    assert result.status is Status.FAIL
    assert result.measured["distance_m"] == pytest.approx(1.0)


def test_lidar_evidence_near_the_footprint_is_reported() -> None:
    # Row 15 is y 9-10; col 19 is x 14-15: 1 m east of the footprint's east edge.
    evidence = site(terrain=terrain(ndsm_cells=((15, 19), (0, 0))))
    result = check(proposal(), "building_separation", evidence)
    assert result.status is Status.UNKNOWN
    assert result.measured["lidar_cells_over_2m_within_2m"] == 1


@pytest.mark.parametrize(
    ("footprint", "area", "status"),
    [
        (rect(5, 5, 13, 11), None, Status.PASS),  # 48 m² outside the walls: under 70 inside
        (rect(5, 5, 13, 11), 37.4, Status.PASS),  # 0.4 m walls: under 70 whatever the walls
        (rect(2, 2, 11, 10.5), None, Status.UNKNOWN),  # 76.5 m² outside: depends on the walls
        (rect(2, 2, 11, 10.5), 66.0, Status.PASS),
        (rect(2, 2, 11, 10.5), 1.0, Status.FAIL),  # less than even 0.6 m walls could leave
        (rect(2, 2, 11, 10.5), 63.1, Status.UNKNOWN),  # 0.4 m walls: possible, not typical
        (rect(2, 2, 11, 10.5), 70.5, Status.FAIL),
        (rect(2, 2, 11, 10.5), 80.0, Status.FAIL),  # more than the footprint: impossible
        (rect(2, 2, 11, 11), None, Status.UNKNOWN),  # 81 m²: 0.45 m straw bale leaves 65.6
        (rect(2, 2, 14, 12), 60.0, Status.FAIL),  # 120 m²: no realistic wall makes that 70
    ],
)
def test_floor_area_is_checked_against_the_measured_footprint(
    footprint: Ring, area: float | None, status: Status
) -> None:
    result = check(proposal(footprint=footprint, floor_area_m2=area), "floor_area")
    assert result.status is status
    assert result.measured["footprint_area_m2"] > 0


def test_a_stated_area_too_small_for_a_small_footprint_is_flagged_not_failed() -> None:
    """Under 70 m² outside the walls, the inside is under 70 whatever is stated."""
    result = check(proposal(footprint=rect(5, 5, 13, 11), floor_area_m2=1.0), "floor_area")
    assert result.status is Status.PASS
    assert "Check the stated value" in result.detail


@pytest.mark.parametrize(
    ("storeys", "status"), [(None, Status.UNKNOWN), (1, Status.PASS), (2, Status.FAIL)]
)
def test_single_storey(storeys: int | None, status: Status) -> None:
    assert check(proposal(storeys=storeys), "single_storey").status is status


@pytest.mark.parametrize(
    ("height", "status"), [(None, Status.UNKNOWN), (4.0, Status.PASS), (4.2, Status.FAIL)]
)
def test_height(height: float | None, status: Status) -> None:
    assert check(proposal(height_above_floor_m=height), "height").status is status


def test_floor_level_is_measured_from_the_lowest_ground_under_the_footprint() -> None:
    # Footprint x 5-13 on ground rising 0.02 m/m: 100.10 at the west wall, 100.26 east.
    result = check(proposal(floor_level_m=100.9), "floor_level")
    assert result.measured["lowest_ground_m"] == pytest.approx(100.10)
    assert result.measured["highest_ground_m"] == pytest.approx(100.26)
    assert result.measured["height_above_lowest_m"] == pytest.approx(0.80)
    assert result.status is Status.PASS


def test_floor_level_samples_the_ground_under_the_walls_not_just_cell_centres() -> None:
    """On a steep slope the lowest ground is at the downhill wall, between centres."""
    xs = np.arange(-5, 45, dtype=np.float64) + 0.5
    dem = np.tile(100.0 + 0.3 * xs, (30, 1)).astype(np.float64)
    steep = TerrainGrid((-5.0, -5.0, 45.0, 25.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    footprint = rect(5.51, 5, 13.51, 11)
    floor = 100.0 + 0.3 * 6.5 + 0.95  # 0.95 m above the lowest centre inside (x 6.5)
    result = check(
        proposal(footprint=footprint, floor_level_m=floor), "floor_level", site(terrain=steep)
    )
    assert result.measured["lowest_ground_m"] == pytest.approx(100.0 + 0.3 * 5.51)
    assert result.status is Status.FAIL


@pytest.mark.parametrize(
    ("floor", "status"),
    [(None, Status.UNKNOWN), (101.2, Status.FAIL), (100.2, Status.UNKNOWN), (99.5, Status.UNKNOWN)],
)
def test_floor_level_limits(floor: float | None, status: Status) -> None:
    """More than 1 m above the lowest ground fails. A floor below the existing ground
    needs a cut, which the exemption doesn't forbid and the LiDAR can't show."""
    assert check(proposal(floor_level_m=floor), "floor_level").status is status


def test_overlapping_a_preservation_area_fails() -> None:
    garden = site(preservation_areas=(rect(10, 8, 16, 14),))
    result = check(proposal(), "preservation_areas", garden)
    assert result.status is Status.FAIL
    assert result.measured["overlap_m2"] == pytest.approx(9.0)


def test_any_failure_fails_the_report_and_unknown_beats_pass() -> None:
    assert evaluate(proposal(storeys=2), site()).status is Status.FAIL
    assert evaluate(proposal(), site()).status is Status.UNKNOWN  # no confirmed buildings


def test_a_report_cannot_be_overridden() -> None:
    report = evaluate(proposal(storeys=2), site())
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.checks = ()  # type: ignore[misc]


def test_every_check_cites_its_rule() -> None:
    report = evaluate(proposal(), site())
    assert all(c.rule for c in report.checks)
    assert "Schedule 1A" in check(proposal(), "floor_area").rule


def test_a_confirmed_empty_site_passes_building_separation() -> None:
    result = check(proposal(), "building_separation", site(buildings_confirmed=True))
    assert result.status is Status.PASS


def test_overlapping_preservation_areas_are_not_counted_twice() -> None:
    garden = site(preservation_areas=(rect(10, 8, 16, 14), rect(10, 8, 16, 14)))
    assert check(proposal(), "preservation_areas", garden).measured["overlap_m2"] == pytest.approx(
        9.0
    )


def test_measurements_cannot_be_edited() -> None:
    result = check(proposal(), "floor_area")
    with pytest.raises(TypeError):
        result.measured["footprint_area_m2"] = 1.0  # type: ignore[index]


@pytest.mark.parametrize(
    "bad",
    [
        {"floor_level_m": float("nan")},
        {"floor_area_m2": -1.0},
        {"floor_area_m2": True},
        {"height_above_floor_m": True},
        {"floor_level_m": False},
        {"floor_area_m2": float("inf")},
        {"height_above_floor_m": 0.0},
        {"storeys": 0},
    ],
)
def test_impossible_proposal_values_are_rejected(bad: dict[str, float]) -> None:
    with pytest.raises(InvalidProposal):
        evaluate(proposal(**bad), site())


def test_a_footprint_beyond_the_terrain_is_rejected() -> None:
    with pytest.raises(InvalidProposal, match="terrain"):
        evaluate(proposal(footprint=rect(40, 5, 48, 11)), site())


def test_setbacks_use_the_outline_but_floor_area_uses_the_walls() -> None:
    """Eaves count towards how close the building comes, not towards its floor area."""
    walls = rect(3, 5, 11, 11)  # 48 m², 3 m from the west boundary
    eaves = rect(2.5, 4.5, 11.5, 11.5)  # 0.5 m overhang: 2.5 m from it
    with_eaves = proposal(footprint=walls, outline=eaves)
    assert check(with_eaves, "title_boundary_setback").measured["distance_m"] == pytest.approx(2.5)
    assert check(with_eaves, "floor_area").measured["footprint_area_m2"] == pytest.approx(48.0)


def test_an_outline_must_contain_the_wall_footprint() -> None:
    with pytest.raises(InvalidProposal, match="outline"):
        evaluate(proposal(outline=rect(5, 5, 9, 9)), site())


def test_far_listed_buildings_pass_only_if_the_list_is_confirmed_complete() -> None:
    listed = (rect(30, 5, 36, 12),)
    unconfirmed = check(proposal(), "building_separation", site(confirmed_buildings=listed))
    assert unconfirmed.status is Status.UNKNOWN
    confirmed = site(confirmed_buildings=listed, buildings_confirmed=True)
    assert check(proposal(), "building_separation", confirmed).status is Status.PASS


def test_a_close_listed_building_fails_whether_or_not_the_list_is_complete() -> None:
    near = site(confirmed_buildings=(rect(14, 5, 18, 11),))
    assert check(proposal(), "building_separation", near).status is Status.FAIL
