"""Tests for button_nz.agent.observe: LiDAR observations in the model's local frame."""

import numpy as np
import pytest

from button_nz.agent.conversation import Observe
from button_nz.agent.loop import DesignSite
from button_nz.agent.observe import OBSERVATION_TOOLS, ObservationError, observe
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext
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
    assert "min_m: 1.50" in result.text  # NZVD2016 101.55
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


def test_inspect_elevation_takes_a_local_polygon(site: DesignSite) -> None:
    polygon = [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]]
    result = observe(site, Observe("inspect_elevation", {"polygon": polygon}))
    assert result.png is None
    assert "relief_m: 0.90" in result.text  # cell centres 1015.5..1024.5 east


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
