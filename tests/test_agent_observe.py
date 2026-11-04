"""Tests for button_nz.agent.observe: LiDAR observations in the model's local frame."""

from dataclasses import replace

import numpy as np
import pytest
from shapely import Polygon

from button_nz.agent.conversation import Observe
from button_nz.agent.loop import DesignSite
from button_nz.agent.observe import OBSERVATION_TOOLS, ObservationError, observe, standard_views
from button_nz.agent.room import describe_room
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext, ground_range
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

PARCEL: Ring = (
    (1000.0, 2000.0),
    (1040.0, 2000.0),
    (1040.0, 2020.0),
    (1000.0, 2020.0),
    (1000.0, 2000.0),
)


@pytest.fixture
def site() -> DesignSite:
    """40 m x 20 m of ground rising 0.1 m per metre east, framed on its centre (1020, 2010)."""
    xs = np.arange(40, dtype=np.float64) + 0.5
    dem = np.tile(100.0 + 0.1 * xs, (20, 1))
    grid = TerrainGrid(
        (1000.0, 2000.0, 1040.0, 2020.0), 1.0, dem, np.zeros_like(dem), ("synthetic",)
    )
    frame = LocalFrame.centred_on(grid.bbox)
    return DesignSite(scene_input(grid, frame, [PARCEL]), frame, SiteContext((PARCEL,), grid))


def test_views_come_back_as_images_with_their_numbers(site: DesignSite) -> None:
    result = observe(site, Observe("render_height_map", {"mode": "slope"}))
    assert result.png is not None and result.png.startswith(b"\x89PNG")
    assert "max_slope_deg" in result.text
    assert "parcel" in result.text  # the outlines drawn on the view are explained


def test_coordinates_are_in_the_local_frame(site: DesignSite) -> None:
    # Local (-10, 0) to (10, 0) is NZTM (1010, 2010) to (1030, 2010): 2 m of rise.
    result = observe(site, Observe("render_cross_section", {"start": [-10, 0], "end": [10, 0]}))
    assert "relief_m: 2.00" in result.text
    assert "(-10.0, 0.0) to (10.0, 0.0)" in result.text
    assert "0.0 m: 0.95" in result.text  # each sample as script z: 101.00 - 100.05
    assert "20.0 m: 2.95" in result.text
    assert "1010" not in result.text  # NZTM never leaks into the model's frame


def test_heights_are_given_in_the_scripts_z(site: DesignSite) -> None:
    """z = NZVD2016 - datum; the datum is the lowest ground, 100.05 m."""
    polygon = [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]
    result = observe(site, Observe("inspect_elevation", {"polygon": polygon}))
    assert "min_m: 1.45" in result.text  # NZVD2016 101.50, at the polygon's west edge
    assert "above the scene datum" in result.text
    contours = observe(site, Observe("render_contours", {"interval_m": 0.5}))
    assert "min_m: 0.00" in contours.text
    assert "NZVD2016" not in contours.text


@pytest.mark.parametrize(
    "request_",
    [
        Observe("render_cross_section", {"start": [0, 0], "end": [200, 0]}),
        Observe("inspect_elevation", {"polygon": [[10, 0], [30, 0], [30, 5], [10, 0]]}),
    ],
)
def test_requests_off_the_terrain_say_where_it_is_locally(
    site: DesignSite, request_: Observe
) -> None:
    with pytest.raises(ObservationError) as error:
        observe(site, request_)
    message = str(error.value)
    assert "outside the terrain" in message
    assert "x -19.5..19.5, y -9.5..9.5" in message
    assert "1020" not in message and "2010" not in message  # no NZTM


def test_inspected_ground_is_what_the_floor_level_check_measures(site: DesignSite) -> None:
    """A floor set at the reported max_m must not be below the ground the evaluator finds."""
    polygon = [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]
    result = observe(site, Observe("inspect_elevation", {"polygon": polygon}))
    footprint = Polygon([site.frame.to_nztm((x, y)) for x, y in polygon])
    low, high = ground_range(footprint, site.context.terrain)
    datum = site.scene["frame"]["datum_m"]
    assert f"min_m: {low - datum:.2f}" in result.text
    assert f"max_m: {high - datum:.2f}" in result.text
    assert f"relief_m: {high - low:.2f}" in result.text


def test_a_polygon_narrower_than_a_cell_still_gets_its_ground_range(site: DesignSite) -> None:
    sliver = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.1]]
    result = observe(site, Observe("inspect_elevation", {"polygon": sliver}))
    assert "min_m" in result.text and "max_m" in result.text


def test_inspect_elevation_takes_a_local_polygon(site: DesignSite) -> None:
    polygon = [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]
    result = observe(site, Observe("inspect_elevation", {"polygon": polygon}))
    assert result.png is None
    assert "relief_m: 1.00" in result.text  # its edges, 1015..1025 east, as floor_level samples


def test_every_offered_tool_runs(site: DesignSite) -> None:
    arguments = {
        "render_hillshade": {"azimuth_deg": 270, "altitude_deg": 30},
        "render_contours": {"interval_m": 0.5},
        "render_height_map": {"mode": "above_ground"},
        "render_cross_section": {"start": [0, -5], "end": [0, 5]},
        "inspect_elevation": {"polygon": [[-2, -2], [2, -2], [2, 2], [-2, -2]]},
    }
    assert set(arguments) == {t["function"]["name"] for t in OBSERVATION_TOOLS}
    for tool, args in arguments.items():
        assert observe(site, Observe(tool, args)).text


def test_the_contour_schema_asks_for_a_positive_interval() -> None:
    (contours,) = [t for t in OBSERVATION_TOOLS if t["function"]["name"] == "render_contours"]
    assert contours["function"]["parameters"]["properties"]["interval_m"]["exclusiveMinimum"] == 0


@pytest.mark.parametrize(
    "request_",
    [
        Observe("render_everything", {}),
        Observe("render_height_map", {"mode": "colourful"}),
        Observe("render_cross_section", {"start": [0, 0]}),
        Observe("render_cross_section", {"start": [0, 0], "end": [200, 0]}),
        Observe("render_contours", {"interval_m": 0}),
    ],
)
def test_bad_requests_are_feedback(site: DesignSite, request_: Observe) -> None:
    with pytest.raises(ObservationError):
        observe(site, request_)


@pytest.fixture
def awkward() -> DesignSite:
    """A frame whose origin isn't exact in binary: the west edge the model is told,
    converted back to NZTM, lands a hair outside the grid."""
    xs = np.arange(50, dtype=np.float64) + 0.5
    dem = np.tile(100.0 + 0.1 * xs, (20, 1))
    grid = TerrainGrid(
        (1542024.0, 2000.0, 1542074.0, 2020.0), 1.0, dem, np.zeros_like(dem), ("synthetic",)
    )
    frame = LocalFrame(origin=(1542050.3599999999, 2010.0))
    ring: Ring = (
        (1542024.0, 2000.0),
        (1542074.0, 2000.0),
        (1542074.0, 2020.0),
        (1542024.0, 2020.0),
        (1542024.0, 2000.0),
    )
    return DesignSite(scene_input(grid, frame, [ring]), frame, SiteContext((ring,), grid))


def test_points_on_the_edge_the_model_is_told_are_on_the_terrain(awkward: DesignSite) -> None:
    west = -25.86  # what the extent says, rounded
    profile = observe(awkward, Observe("render_cross_section", {"start": [west, 0], "end": [0, 0]}))
    assert "Terrain profile" in profile.text
    square = [[west, -2], [west + 4, -2], [west + 4, 2], [west, 2], [west, -2]]
    inspected = observe(awkward, Observe("inspect_elevation", {"polygon": square}))
    assert "cells" in inspected.text and "mean_slope_deg" in inspected.text


def test_the_standard_views_are_the_shape_what_stands_on_it_and_a_profile(
    site: DesignSite,
) -> None:
    views = standard_views(site)
    assert [(request.tool, dict(request.arguments)) for request, _ in views][:3] == [
        ("render_hillshade", {}),
        ("render_contours", {"interval_m": 0.25}),
        ("render_height_map", {"mode": "above_ground"}),
    ]
    assert [request.tool for request, _ in views][3:] == [
        "render_cross_section",
        "inspect_elevation",  # the room's one rectangle 3 m wide or more
        "inspect_elevation",  # the whole room
    ]
    for request, observation in views[:4]:  # each exactly as the model asking for it gets it
        assert observation == observe(site, request)
        assert observation.png is not None and observation.png.startswith(b"\x89PNG")
    for request, observation in views[4:]:  # the same numbers, under a label saying where
        assert observation.png is None
        assert observation.text.endswith(observe(site, request).text)


def test_the_ground_under_each_largest_rectangle_is_given_at_its_printed_corners(
    site: DesignSite,
) -> None:
    """The polygon is the rectangle's corners as the prompt prints them: asking
    for the same polygon gets the same numbers."""
    request, observation = standard_views(site)[4]
    corners = ", ".join(f"({x:.2f}, {y:.2f})" for x, y in request.arguments["polygon"])
    assert f"largest rectangle 1, corners {corners}" in observation.text
    assert corners in describe_room(site.context, site.frame.to_local)
    assert "relief_m: 3.5" in observation.text  # 35.5 m of ground rising 0.1 m per metre


def test_the_ground_range_under_the_whole_room_is_given(site: DesignSite) -> None:
    """The room spans x -18..18 locally: NZTM x 1002..1038, ground 100.2..103.8 m,
    so z 0.15..3.75 above the datum (100.05 m)."""
    _, observation = standard_views(site)[5]
    assert "the whole room" in observation.text
    assert "ground z from 0.15 to 3.75" in observation.text
    assert "part 1 of 1" in observation.text


def test_a_room_in_parts_gives_each_part_and_the_range_over_all(site: DesignSite) -> None:
    """Two sections side by side: the room is split by the line between them."""
    west: Ring = ((1000.0, 2000.0), (1020.0, 2000.0), (1020.0, 2020.0), (1000.0, 2020.0))
    east: Ring = ((1020.0, 2000.0), (1040.0, 2000.0), (1040.0, 2020.0), (1020.0, 2020.0))
    sections = tuple(ring + (ring[0],) for ring in (west, east))
    split = replace(site, context=replace(site.context, parcels=sections))
    room = [o.text for _, o in standard_views(split) if "room, part" in o.text]
    assert len(room) == 2
    assert "part 1 of 2" in room[0] and "part 2 of 2" in room[1]
    assert "ground z from 0.15 to 3.75" in room[0]  # over both parts: stated once


def test_the_profile_runs_the_length_of_the_rooms_largest_rectangle(site: DesignSite) -> None:
    """The 40 x 20 m parcel less its 2 m setback is x -18..18, y -8..8 locally,
    so the profile runs west to east along y = 0, rising 0.1 m per metre."""
    request, observation = standard_views(site)[3]
    (x0, y0), (x1, y1) = sorted((request.arguments["start"], request.arguments["end"]))
    assert y0 == pytest.approx(0, abs=0.5) and y1 == pytest.approx(0, abs=0.5)
    assert x0 == pytest.approx(-18, abs=0.5) and x1 == pytest.approx(18, abs=0.5)
    assert "relief_m: 3.5" in observation.text


def test_with_no_room_for_a_dwelling_there_is_no_profile(site: DesignSite) -> None:
    """A 5 m square title has no room inside its 2 m setbacks: no line to draw."""
    small: Ring = (
        (1010.0, 2005.0),
        (1015.0, 2005.0),
        (1015.0, 2010.0),
        (1010.0, 2010.0),
        (1010.0, 2005.0),
    )
    tiny = replace(site, context=replace(site.context, parcels=(small,)))
    assert [request.tool for request, _ in standard_views(tiny)] == [  # and no ground to give
        "render_hillshade",
        "render_contours",
        "render_height_map",
    ]


def test_every_rectangle_given_is_one_the_prompt_lists(site: DesignSite) -> None:
    """Three sections side by side: room for three rectangles, and the prompt
    lists each one whose ground comes with the brief, at the same corners."""
    xs = (1000.0, 1014.0, 1027.0, 1040.0)
    sections = tuple(
        ((w, 2000.0), (e, 2000.0), (e, 2020.0), (w, 2020.0), (w, 2000.0))
        for w, e in zip(xs, xs[1:], strict=False)
    )
    thirds = replace(site, context=replace(site.context, parcels=sections))
    prompt = describe_room(thirds.context, thirds.frame.to_local)
    given = [r for r, o in standard_views(thirds) if "largest rectangle" in o.text]
    assert len(given) == 3
    for request in given:
        corners = ", ".join(f"({x:.2f}, {y:.2f})" for x, y in request.arguments["polygon"])
        assert corners in prompt


def test_a_room_with_a_hole_says_the_ground_given_includes_it(site: DesignSite) -> None:
    """A kept area inside the room cuts a hole in it. An observation's polygon
    has no holes, so the part's numbers and the range over the whole room are
    both the ground inside its outline, the hole included, and say so."""
    kept: Ring = (
        (1018.0, 2008.0),
        (1022.0, 2008.0),
        (1022.0, 2012.0),
        (1018.0, 2012.0),
        (1018.0, 2008.0),
    )
    holed = replace(site, context=replace(site.context, preservation_areas=(kept,)))
    (part,) = [o.text for _, o in standard_views(holed) if "room, part" in o.text]
    whole, label = part.splitlines()[:2]
    assert "the areas cut out of it included" in whole
    assert "the areas cut out of it included" in label
    assert "ground z from 0.15 to 3.75" in whole
