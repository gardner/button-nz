"""Tests for button_nz.agent.placement: where a dwelling can stand, solved
before a script is written, and measured as the evaluator measures it."""

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray
from shapely import LineString, Polygon

import button_nz.agent.placement as placement_module
from button_nz.agent.placement import (
    MAX_CONFIRMED,
    PROMPT_PLANS,
    TARGET_MARGIN_M,
    Placement,
    describe_placements,
    floor_range_text,
    least_ground_range,
    solve,
)
from button_nz.agent.site import DesignSite
from button_nz.blender_worker.scene_input import scene_input
from button_nz.demo_site import DEMO_SITE_DIR, load_demo_site
from button_nz.evaluation import Check, Footprint, Proposal, SiteContext, Status, evaluate
from button_nz.evaluation.checks import MAX_FLOOR_ABOVE_GROUND_M
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Point, Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.confirm import Decision, Survey, confirmed
from button_nz.sites.frontages import Frontage

TITLE: Ring = ((0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0), (0.0, 0.0))
SITING = {
    "within_site",
    "title_boundary_setback",
    "section_boundary_setback",
    "building_separation",
    "floor_level",
    "preservation_areas",
}
DEMO_TERRAIN = Path(__file__).parent / "data" / "demo-site-terrain.json"
# The owner's decisions on the demo site's survey (d93466c930ab238f), as the
# production run that placed the Methven recorded them: two areas kept clear,
# nothing built on the site.
OWNER_DECISIONS = {
    "1": "ignore",
    "2": "ignore",
    "3": "keep_clear",
    "4": "ignore",
    "5": "keep_clear",
}


def test_every_placement_passes_the_evaluators_siting_checks() -> None:
    site = _site(slope_x=0.05)
    found = solve(site, 9.0, 6.0, eaves_m=0.6).placements
    assert found
    for placement in found:
        for check in _siting(placement, site):
            assert check.status is Status.PASS, (check.name, check.detail)


def test_placements_aim_for_the_margin_where_the_room_allows() -> None:
    (best, *_) = solve(_site(), 9.0, 6.0, eaves_m=0.6).placements
    assert best.margin_m >= TARGET_MARGIN_M
    assert best.margin_m == best.clearances["title_boundary_m"]  # the only 2 m line here


def test_the_eaves_count_towards_the_setback() -> None:
    narrow = ((0.0, 0.0), (11.0, 0.0), (11.0, 30.0), (0.0, 30.0), (0.0, 0.0))  # 7 m inside
    site = _site(title=narrow)
    assert solve(site, 9.0, 6.0, eaves_m=0.0).placements  # 6 m walls fit 7 m of room
    assert not solve(site, 9.0, 6.0, eaves_m=0.6).placements  # 7.2 m of outline doesn't


def test_the_floor_range_is_what_the_floor_level_check_passes() -> None:
    site = _site(slope_x=0.05)
    for placement in solve(site, 9.0, 6.0).placements:
        low, high = placement.floor_range_m
        assert high - low <= MAX_FLOOR_ABOVE_GROUND_M
        assert high == placement.lowest_ground_m + MAX_FLOOR_ABOVE_GROUND_M
        for floor in (low, high):
            assert _floor_level(placement, site, floor) is Status.PASS
        assert _floor_level(placement, site, high + 0.01) is Status.FAIL
        assert _floor_level(placement, site, low - 0.01) is Status.UNKNOWN  # a cut


def test_on_a_slope_a_long_plan_is_turned_across_it() -> None:
    site = _site(slope_x=0.15)  # 1 m of fall in under 7 m eastwards
    found = solve(site, 10.0, 4.0).placements
    assert found
    for placement in found:
        west, _, east, _ = placement.walls.bounds
        assert (east - west) * 0.15 <= MAX_FLOOR_ABOVE_GROUND_M + 1e-6


def test_too_steep_a_site_has_no_placement_and_says_how_uneven_it_is() -> None:
    solution = solve(_site(slope_x=0.4), 10.0, 4.0)  # even 4 m across falls 1.6 m
    assert solution.placements == ()
    assert solution.least_ground_range_m is not None
    assert solution.least_ground_range_m > MAX_FLOOR_ABOVE_GROUND_M


def test_a_site_with_no_room_says_so() -> None:
    solution = solve(_site(), 40.0, 30.0)
    assert solution.placements == ()
    assert solution.least_ground_range_m is None


def test_section_lines_are_kept_clear_so_they_pass() -> None:
    a: Ring = ((0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0), (0.0, 0.0))
    b: Ring = ((0.0, 15.0), (20.0, 15.0), (20.0, 30.0), (0.0, 30.0), (0.0, 15.0))
    site = _site(parcels=(a, b))
    found = solve(site, 9.0, 6.0, eaves_m=0.6).placements
    assert found
    for placement in found:
        assert placement.clearances["section_line_m"] >= 2.0
        assert not placement.outline.intersects(LineString([(0, 15), (20, 15)]).buffer(2.0 - 1e-6))


def test_section_lines_can_be_only_not_crossed() -> None:
    a: Ring = ((0.0, 0.0), (20.0, 0.0), (20.0, 12.0), (0.0, 12.0), (0.0, 0.0))
    b: Ring = ((0.0, 12.0), (20.0, 12.0), (20.0, 24.0), (0.0, 24.0), (0.0, 12.0))
    site = _site(parcels=(a, b))  # 10 m of room each side: 2 m clear of the line leaves 8 m
    assert not solve(site, 9.0, 9.0).placements
    lenient = solve(site, 9.0, 9.0, section_clear_m=0.0).placements
    assert lenient
    line = LineString([(0, 12), (20, 12)])
    assert all(not p.walls.buffer(-1e-6).intersects(line) for p in lenient)


def test_listed_buildings_and_kept_areas_are_respected() -> None:
    house: Ring = ((4.0, 4.0), (16.0, 4.0), (16.0, 12.0), (4.0, 12.0), (4.0, 4.0))
    tree: Ring = ((2.0, 20.0), (8.0, 20.0), (8.0, 28.0), (2.0, 28.0), (2.0, 20.0))
    site = _site(buildings=(house,), keep_clear=(tree,))
    found = solve(site, 8.0, 5.0).placements
    assert found
    for placement in found:
        assert placement.outline.distance(Polygon(house)) >= 2.0
        assert not placement.outline.intersects(Polygon(tree).buffer(-1e-6))
        assert placement.clearances["building_m"] >= 2.0
        assert {c.name: c.status for c in _siting(placement, site)}["building_separation"] is (
            Status.PASS
        )


def test_the_placements_are_distinct_spots_best_first() -> None:
    found = solve(_site(), 6.0, 4.0, count=3).placements
    assert len(found) == 3
    for i, first in enumerate(found):
        for second in found[i + 1 :]:
            assert first.walls.intersection(second.walls).area < 0.5 * first.walls.area
    keys = [min(p.margin_m, TARGET_MARGIN_M) for p in found]
    assert keys == sorted(keys, reverse=True)


def test_the_street_edge_is_measured_and_farther_is_preferred() -> None:
    street = Frontage("Victory Street", True, (((0.0, 0.0), (20.0, 0.0)),))
    found = solve(_site(), 6.0, 4.0, frontages=(street,)).placements
    assert found
    best = found[0]
    assert best.clearances["street_edge_m"] == best.walls.distance(LineString([(0, 0), (20, 0)]))
    assert best.walls.centroid.y > 15.0  # the back of the section


def test_the_demo_site_holds_the_methven_within_every_siting_rule() -> None:
    # The final take's Methven (15 x 4.2 m) failed floor level at 1.24 m above
    # the lowest ground, 0.75 m from a section line: the site has room for it.
    site = _demo_context()
    found = solve(site, 15.0, 4.2, eaves_m=0.6).placements
    assert found
    for placement in found:
        for check in _siting(placement, site):
            assert check.status is Status.PASS, (check.name, check.detail)
        assert placement.clearances["section_line_m"] >= 2.0
        low, high = placement.floor_range_m
        assert low <= high


def test_the_demo_site_has_no_room_for_a_wide_plan_clear_of_its_section_lines() -> None:
    assert solve(_demo_context(), 10.0, 7.0, eaves_m=0.6).placements == ()


def test_the_solver_is_fast_on_the_demo_site() -> None:
    site = _demo_context()
    started = time.perf_counter()
    solve(site, 15.0, 4.2, eaves_m=0.6)
    assert time.perf_counter() - started < 1.0


def test_the_prompt_gives_each_placement_in_local_coordinates_and_scene_z() -> None:
    site = _design_site(_site(slope_x=0.05), origin=(10.0, 15.0))
    text = describe_placements(site, Footprint("Studio", 9.0, 6.0))
    datum = site.scene["frame"]["datum_m"]
    (best, *_) = solve(site.context, 9.0, 6.0, eaves_m=0.6).placements
    cx, cy = site.frame.to_local((best.walls.centroid.x, best.walls.centroid.y))
    assert f"centre ({cx:.2f}, {cy:.2f})" in text
    assert f"{best.clearances['title_boundary_m']:.2f} m from the title boundary" in text
    low = math.ceil((best.floor_range_m[0] - datum) * 100) / 100
    high = math.floor((best.floor_range_m[1] - datum) * 100) / 100
    assert f"floor underside at z {low:.2f} to {high:.2f}" in text
    assert "9 × 6 m" in text and "0.6 m eaves" in text
    assert text.count("centre (") == 3


def test_a_bespoke_design_gets_a_placement_for_each_plain_plan() -> None:
    text = describe_placements(_design_site(_site()))
    for length, width in PROMPT_PLANS:
        assert f"{length:g} × {width:g} m" in text
    assert text.count("centre (") == len(PROMPT_PLANS)


def test_the_prompt_says_when_nothing_can_be_placed() -> None:
    text = describe_placements(_design_site(_site(slope_x=0.4)), Footprint("Long", 10.0, 4.0))
    assert "10 × 4 m" in text and "no placement" in text and "floor level" in text
    assert "the search" in text and "may" in text  # a sampled miss, not an impossibility
    assert "wherever it fits" not in text and "fits nowhere" not in text


def _design_site(context: SiteContext, origin: Point = (0.0, 0.0)) -> DesignSite:
    frame = LocalFrame(origin=origin)
    return DesignSite(scene_input(context.terrain, frame, list(context.parcels)), frame, context)


def _siting(placement: Placement, site: SiteContext) -> list[Check]:
    proposal = Proposal(
        footprint=_ring(placement.walls),
        outline=_ring(placement.outline),
        floor_level_m=placement.floor_range_m[0],
    )
    return [c for c in evaluate(proposal, site).checks if c.name in SITING]


def _floor_level(placement: Placement, site: SiteContext, floor: float) -> Status:
    proposal = Proposal(footprint=_ring(placement.walls), floor_level_m=floor)
    (check,) = [c for c in evaluate(proposal, site).checks if c.name == "floor_level"]
    return check.status


def _ring(polygon: Polygon) -> Ring:
    return tuple((float(x), float(y)) for x, y in polygon.exterior.coords)


def _site(
    title: Ring = TITLE,
    parcels: tuple[Ring, ...] | None = None,
    slope_x: float = 0.0,
    buildings: tuple[Ring, ...] = (),
    keep_clear: tuple[Ring, ...] = (),
    slope: tuple[float, float] | None = None,
) -> SiteContext:
    """A site whose ground rises ``slope_x`` m per m eastwards (or by
    ``slope``, m per m east and north), on a 1 m grid 5 m past the title."""
    rings = parcels or (title,)
    xs = [x for ring in rings for x, _ in ring]
    ys = [y for ring in rings for _, y in ring]
    west, south, east, north = min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5
    cols, rows = int(east - west), int(north - south)
    east_m, north_m = slope or (slope_x, 0.0)
    xs = west + np.arange(cols, dtype=np.float64) + 0.5
    ys = north - np.arange(rows, dtype=np.float64) - 0.5  # row 0 is the north edge
    dem: NDArray[np.float64] = 100.0 + east_m * xs[None, :] + north_m * ys[:, None]
    grid = TerrainGrid((west, south, east, north), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    return SiteContext(
        parcels=rings,
        terrain=grid,
        confirmed_buildings=buildings,
        buildings_confirmed=True,
        preservation_areas=keep_clear,
    )


def _demo_context() -> SiteContext:
    """35 Victory Street as the owner decided it, on its real LiDAR."""
    raw = json.loads(DEMO_TERRAIN.read_text(encoding="utf-8"))
    dem: NDArray[np.float64] = np.array(raw["dem"], dtype=np.float64)
    ndsm: NDArray[np.float64] = np.array(raw["ndsm"], dtype=np.float64)
    grid = TerrainGrid(tuple(raw["bbox"]), raw["cell_m"], dem, ndsm, tuple(raw["sources"]))
    demo = load_demo_site()
    parcels = tuple(parcel.ring for parcel in demo.parcels)
    frame = LocalFrame.centred_on(demo.extent_nztm)
    context = SiteContext(parcels=parcels, terrain=grid)
    site = DesignSite(scene_input(grid, frame, parcels), frame, context)
    survey = Survey.read(DEMO_SITE_DIR / "survey.geojson")
    assert survey is not None and survey.id == "d93466c930ab238f"
    decisions = {k: Decision(v) for k, v in OWNER_DECISIONS.items()}
    return confirmed(site, survey, decisions, complete=True).context


def test_the_evaluator_is_asked_at_most_a_bounded_number_of_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cells 1 m apart span exactly 1 m here, but the outline's crossings
    # reach past them: every candidate passes the quick test and fails the
    # evaluator, so the search stops rather than ask about all of them.
    asked: list[int] = []
    confirm = placement_module.confirmed_placement

    def counted(*args: Any) -> Placement | None:
        asked.append(1)
        return confirm(*args)

    monkeypatch.setattr(placement_module, "confirmed_placement", counted)
    assert solve(_site(slope_x=0.2), 9.0, 6.0, eaves_m=0.6).placements == ()
    assert len(asked) == MAX_CONFIRMED


def test_a_section_at_the_largest_size_a_site_may_be_is_searched_fast() -> None:
    block: Ring = ((0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0), (0.0, 0.0))
    site = _site(title=block, slope_x=0.02)
    started = time.perf_counter()
    found = solve(site, 15.0, 4.2, eaves_m=0.6).placements
    assert time.perf_counter() - started < 1.5  # about 0.6 s here, on a 0.6 m grid
    assert len(found) == 3


def test_the_least_ground_range_is_found_without_the_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _site(slope_x=0.4)
    expected = solve(site, 10.0, 4.0, section_clear_m=0.0).least_ground_range_m

    def refuse(*_: Any) -> None:
        raise AssertionError("the evaluator was asked")

    monkeypatch.setattr(placement_module, "confirmed_placement", refuse)
    assert least_ground_range(site, 10.0, 4.0, section_clear_m=0.0) == expected


def test_a_finer_angle_step_finds_a_plan_turned_to_contours_between_the_coarse_ones() -> None:
    # The ground falls 0.23 m per m at 7.5° past north: square to the title, a
    # 15 x 4.2 m plan is never turned along the contours (every 15°).
    fall = (math.cos(math.radians(97.5)), math.sin(math.radians(97.5)))
    block: Ring = ((0.0, 0.0), (60.0, 0.0), (60.0, 60.0), (0.0, 60.0), (0.0, 0.0))
    site = _site(title=block, slope=(0.23 * fall[0], 0.23 * fall[1]))
    coarse = least_ground_range(site, 15.0, 4.2)
    fine = least_ground_range(site, 15.0, 4.2, angle_step_deg=2.5)
    assert coarse is not None and fine is not None
    assert coarse > MAX_FLOOR_ABOVE_GROUND_M >= fine


def test_a_narrow_floor_range_is_printed_finely_enough_to_hold_a_passing_level() -> None:
    assert floor_range_text(0.24, 1.23) == "0.24 to 1.23"
    assert floor_range_text(0.2401, 1.2299) == "0.25 to 1.22"  # drawn in: both pass
    text = floor_range_text(101.002, 101.004)  # to the cm it would be 101.01 to 101.00
    low, high = (float(v) for v in text.split(" to "))
    assert 101.002 <= low <= high <= 101.004
