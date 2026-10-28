"""Tests for button_nz.lidar against synthetic terrains with known answers."""

import io
import math

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from button_nz.geo.terrain import TerrainGrid
from button_nz.lidar import (
    contours,
    cross_section,
    hillshade,
    inspect_elevation,
    ndsm_map,
    normal_map,
    overlay,
    slope_degrees,
    slope_map,
)

N = 40  # 40 x 40 cells of 1 m over NZTM (0, 0)-(40, 40)
BBOX = (0.0, 0.0, 40.0, 40.0)


def centres() -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    xs = np.arange(N, dtype=np.float64) + 0.5
    ys = N - (np.arange(N, dtype=np.float64) + 0.5)  # row 0 is the north edge
    x, y = np.meshgrid(xs, ys)
    return x, y


def grid(dem: NDArray[np.float64], ndsm: NDArray[np.float64] | None = None) -> TerrainGrid:
    above = np.zeros_like(dem) if ndsm is None else ndsm
    return TerrainGrid(BBOX, 1.0, dem, above, ("synthetic",))


def plane(east: float = 0.0, north: float = 0.0) -> TerrainGrid:
    x, y = centres()
    return grid(100.0 + east * x + north * y)


def image(png: bytes) -> NDArray[np.uint8]:
    pixels: NDArray[np.uint8] = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    return pixels


def test_slope_of_a_plane_is_uniform() -> None:
    slope = slope_degrees(plane(east=0.1))
    assert slope == pytest.approx(np.full((N, N), math.degrees(math.atan(0.1))))


def test_slope_map_reports_its_range() -> None:
    view = slope_map(plane(north=0.2))
    assert view.facts["max_slope_deg"] == pytest.approx(math.degrees(math.atan(0.2)))
    assert view.png.startswith(b"\x89PNG")


def test_hillshade_is_brighter_on_slopes_facing_the_sun() -> None:
    # Sun in the west (azimuth 270): ground rising to the east faces it.
    facing = image(hillshade(plane(east=0.5), azimuth_deg=270, altitude_deg=30).png).mean()
    away = image(hillshade(plane(east=-0.5), azimuth_deg=270, altitude_deg=30).png).mean()
    assert facing > away + 50


def test_contours_of_a_cone_are_circles_at_the_interval() -> None:
    x, y = centres()
    radius = np.hypot(x - 20.0, y - 20.0)
    view = contours(grid(100.0 + radius), interval_m=5.0, scale=1)
    lines = image(view.png).min(axis=2) < 128  # contour pixels are drawn dark
    on_line = radius[lines]
    assert on_line.size > 50
    assert np.all(np.abs(on_line - 5.0 * np.round(on_line / 5.0)) <= 1.0)
    assert view.facts["interval_m"] == 5.0


@pytest.mark.parametrize("interval", [0.0, -0.5, math.nan, math.inf])
def test_contours_need_a_positive_interval(interval: float) -> None:
    with pytest.raises(ValueError, match="interval"):
        contours(plane(east=0.1), interval_m=interval)


def test_normal_map_of_a_plane_is_one_colour() -> None:
    pixels = image(normal_map(plane(east=0.3)).png)
    assert len(np.unique(pixels.reshape(-1, 3), axis=0)) == 1


def test_ndsm_map_reports_above_ground_evidence() -> None:
    above = np.zeros((N, N))
    above[10:13, 10:14] = 7.5
    view = ndsm_map(grid(np.full((N, N), 100.0), above))
    assert view.facts["max_above_ground_m"] == 7.5
    assert view.facts["cells_over_2m"] == 12


def test_cross_section_of_a_plane_follows_it_exactly() -> None:
    section = cross_section(plane(east=0.2), (5.0, 20.0), (35.0, 20.0), step_m=0.5)
    assert section.distances[0] == 0.0 and section.distances[-1] == pytest.approx(30.0)
    assert section.heights == pytest.approx([100.0 + 0.2 * (5.0 + d) for d in section.distances])
    assert section.view.facts["relief_m"] == pytest.approx(6.0)
    assert section.view.png.startswith(b"\x89PNG")


def test_cross_sections_follow_the_rendered_triangles_not_a_bilinear_surface() -> None:
    """Corners 0/1 over 1/0: the mesh's NW-SE diagonal is flat at 0; bilinear says 0.5."""
    saddle = np.array([[0.0, 1.0], [1.0, 0.0]])
    grid = TerrainGrid((0.0, 0.0, 2.0, 2.0), 1.0, saddle, np.zeros_like(saddle), ("synthetic",))
    section = cross_section(grid, (0.5, 1.5), (1.5, 0.5), step_m=0.1)
    assert section.heights == pytest.approx([0.0] * len(section.heights))


def test_a_profile_can_be_labelled_above_a_datum() -> None:
    """Labelled from datum 100, the picture is the one for ground 100 m lower."""
    labelled = cross_section(plane(east=0.2), (5.0, 20.0), (35.0, 20.0), datum_m=100.0)
    x, y = centres()
    lowered = grid(0.2 * x + 0.0 * y)
    assert labelled.view.png == cross_section(lowered, (5.0, 20.0), (35.0, 20.0)).view.png
    assert labelled.view.facts["min_m"] == pytest.approx(101.0)  # facts stay NZVD2016


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((5.0, 20.0), (200.0, 20.0)),  # runs off the east edge
        ((-3.0, 20.0), (5.0, 20.0)),  # starts west of the grid
        ((0.2, 20.0), (5.0, 20.0)),  # inside the bbox but outside the cell centres
        ((5.0, 20.0), (5.0e6, 6.0e6)),  # NZTM-sized coordinates
    ],
)
def test_cross_sections_must_stay_on_the_measured_grid(
    start: tuple[float, float], end: tuple[float, float]
) -> None:
    with pytest.raises(ValueError, match="outside the terrain"):
        cross_section(plane(east=0.2), start, end)


def test_inspect_elevation_rejects_a_polygon_leaving_the_grid() -> None:
    partly_off = ((30.0, 10.0), (60.0, 10.0), (60.0, 20.0), (30.0, 20.0), (30.0, 10.0))
    with pytest.raises(ValueError, match="outside the terrain"):
        inspect_elevation(plane(east=0.1), partly_off)


def test_inspect_elevation_inside_a_polygon() -> None:
    square = ((10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0), (10.0, 10.0))
    stats = inspect_elevation(plane(east=0.1), square)
    # Cell centres 10.5..19.5 east: heights 101.05..101.95.
    assert stats["min_m"] == pytest.approx(101.05)
    assert stats["max_m"] == pytest.approx(101.95)
    assert stats["relief_m"] == pytest.approx(0.9)
    assert stats["cells"] == 100
    assert stats["mean_slope_deg"] == pytest.approx(math.degrees(math.atan(0.1)))


def test_a_polygon_outside_the_grid_raises() -> None:
    far = ((100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 100.0))
    with pytest.raises(ValueError, match="outside the terrain"):
        inspect_elevation(plane(), far)


def test_a_polygon_between_cell_centres_raises() -> None:
    sliver = ((10.6, 10.6), (11.4, 10.6), (11.4, 11.4), (10.6, 10.6))
    with pytest.raises(ValueError, match="no cell"):
        inspect_elevation(plane(), sliver)


def test_overlay_draws_outlines_in_the_views_pixel_space() -> None:
    g = plane(east=0.1)
    square = ((10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0), (10.0, 10.0))
    view = overlay(hillshade(g, scale=4), g, [square], scale=4)
    pixels = image(view.png)
    # NZTM (10, 20) is column 10, row 20 from the north edge: pixel (40, 80).
    red, green, blue = (int(v) for v in pixels[80, 60])  # on the north edge of the square
    assert red > 200 and green < 80 and blue < 80
    assert tuple(pixels[100, 60]) == tuple(
        image(hillshade(g, scale=4).png)[100, 60]
    )  # inside: untouched
    assert view.facts == hillshade(g, scale=4).facts
