"""Tiers 0 and 1 of the relief views: the LiDAR's heights on the aerial's own
pixels, the depth map made from them, and the oblique parallax view."""

import io

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from button_nz.relief import SiteRelief
from button_nz.relief.depth import depth_map
from button_nz.relief.parallax import BACKGROUND, WALL_SHADE, oblique, sway_path


def _relief(surface: NDArray[np.float64], pixel_m: float = 0.25) -> SiteRelief:
    rows, cols = surface.shape
    scale = round(1.0 / pixel_m)
    aerial = np.zeros((rows * scale, cols * scale, 3), dtype=np.uint8)
    return SiteRelief(aerial, surface, 1.0, pixel_m, (0.0, 0.0, float(cols), float(rows)))


def _stripes(rows: int, cols: int) -> NDArray[np.uint8]:
    """A photo whose every row is a different grey, so a row's shift shows."""
    level = (np.arange(rows) * 7 % 250).astype(np.uint8)
    return np.repeat(np.repeat(level[:, None, None], cols, axis=1), 3, axis=2)


class TestHeights:
    def test_on_the_aerials_pixels(self) -> None:
        relief = _relief(np.full((4, 5), 3.0))
        assert relief.heights.shape == (16, 20)
        assert np.allclose(relief.heights, 3.0)

    def test_bilinear_between_cell_centres(self) -> None:
        # Heights rise 1 m per cell eastwards: cell c's centre (c + 0.5 m) is c.
        relief = _relief(np.tile(np.arange(5, dtype=np.float64), (4, 1)))
        row = relief.heights[0]
        # Pixel j's centre is (j + 0.5) x 0.25 m east, so (j + 0.5) / 4 - 0.5 cells.
        inside = slice(2, 18)
        expected = (np.arange(20) + 0.5) / 4 - 0.5
        assert np.allclose(row[inside], expected[inside])

    def test_edges_hold_the_edge_cells_height(self) -> None:
        relief = _relief(np.tile(np.arange(5, dtype=np.float64), (4, 1)))
        row = relief.heights[0]
        assert row[0] == 0.0 and row[-1] == 4.0  # clamped, never extrapolated

    def test_the_aerial_must_cover_the_grid(self) -> None:
        with pytest.raises(ValueError, match="aerial"):
            SiteRelief(np.zeros((10, 10, 3), np.uint8), np.zeros((4, 5)), 1.0, 0.25, (0, 0, 5, 4))


class TestDepthMap:
    def test_sixteen_bit_from_lowest_to_highest(self) -> None:
        surface = np.array([[0.0, 10.0], [5.0, 2.5]])
        depth = depth_map(_relief(surface, pixel_m=1.0))
        with Image.open(io.BytesIO(depth.png16)) as image:
            assert image.mode == "I;16"
            values = np.asarray(image)
        assert values[0, 0] == 0 and values[0, 1] == 65535
        assert values[1, 0] == round(65535 * 0.5)
        assert (depth.low_m, depth.high_m) == (0.0, 10.0)

    def test_preview_is_eight_bit_grey(self) -> None:
        depth = depth_map(_relief(np.array([[0.0, 10.0]]), pixel_m=1.0))
        with Image.open(io.BytesIO(depth.preview)) as image:
            assert image.mode == "L"
            assert np.asarray(image).tolist() == [[0, 255]]

    def test_flat_ground_has_no_range(self) -> None:
        with pytest.raises(ValueError, match="flat"):
            depth_map(_relief(np.zeros((2, 2)), pixel_m=1.0))


class TestOblique:
    def test_straight_down_is_the_photo(self) -> None:
        photo = _stripes(40, 30)
        heights = np.random.default_rng(1).uniform(0, 5, (40, 30))
        assert np.array_equal(oblique(photo, heights, 0.25, tilt_deg=0, bearing_deg=0), photo)

    def test_a_tilt_foreshortens_flat_ground(self) -> None:
        photo = _stripes(100, 10)
        view = oblique(photo, np.zeros((100, 10)), 0.25, tilt_deg=60, bearing_deg=0)
        # cos 60 = 0.5: the ground's 100 rows fill the middle 50.
        assert np.all(view[:24] == BACKGROUND) and np.all(view[76:] == BACKGROUND)
        assert np.array_equal(view[50, 0], photo[50, 0])

    def test_a_raised_block_stands_up_and_hides_whats_behind(self) -> None:
        photo = _stripes(80, 10)
        photo[40:44] = (200, 0, 0)  # a red roof, 1 m deep
        heights = np.zeros((80, 10))
        heights[40:44] = 4.0  # 4 m up
        view = oblique(photo, heights, 0.25, tilt_deg=30, bearing_deg=0)
        red = np.flatnonzero(np.all(view[:, 5] == (200, 0, 0), axis=1))
        shaded = np.flatnonzero(np.all(view[:, 5] == (round(200 * WALL_SHADE), 0, 0), axis=1))
        # The roof rises by 4 sin 30 = 2 m on screen: 8 rows, less the foreshortening.
        flat_row = 40 * np.cos(np.radians(30)) + 40 * (1 - np.cos(np.radians(30)))
        assert red.min() < flat_row - 7
        # Its front edge faces the camera, so it and the wall stretched below it are shaded.
        assert shaded.size > 4 and shaded.min() > red.max()
        # The ground just behind the roof (north of it, further away) is hidden by it.
        assert not np.any(np.all(view[:, 5] == photo[35, 5], axis=1))

    def test_flat_ground_and_slopes_away_are_not_shaded(self) -> None:
        photo = np.full((40, 10, 3), 200, dtype=np.uint8)
        heights = np.tile(np.linspace(5.0, 0.0, 40)[:, None], (1, 10))  # falls towards the camera
        view = oblique(photo, heights, 0.25, tilt_deg=30, bearing_deg=180)  # looking down it
        ground = view[np.any(view != BACKGROUND, axis=2)]
        assert np.all(ground == 200)

    def test_bearing_turns_the_view(self) -> None:
        photo = np.zeros((20, 20, 3), dtype=np.uint8)
        photo[:, :10] = (0, 0, 255)  # west half blue
        view = oblique(photo, np.zeros((20, 20)), 0.25, tilt_deg=0, bearing_deg=90)
        # Looking east, west is at the bottom of the frame.
        assert np.all(view[15, 5:15] == (0, 0, 255)) and np.all(view[4, 5:15] == (0, 0, 0))

    def test_needs_heights_on_the_photos_pixels(self) -> None:
        with pytest.raises(ValueError, match="heights"):
            oblique(np.zeros((4, 4, 3), np.uint8), np.zeros((3, 4)), 0.25, 10, 0)


class TestSwayPath:
    def test_rises_from_flat_sways_and_settles_back(self) -> None:
        path = sway_path(60, tilt_deg=30, sway_deg=10, bearing_deg=20)
        assert len(path) == 60
        assert path[0] == (0.0, 20.0) and path[-1][0] == pytest.approx(0.0, abs=1e-9)
        assert max(tilt for tilt, _ in path) == pytest.approx(30.0)
        bearings = [bearing for _, bearing in path]
        assert min(bearings) == pytest.approx(10.0, abs=0.5)
        assert max(bearings) == pytest.approx(30.0, abs=0.5)
