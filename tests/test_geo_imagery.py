"""Tests for button_nz.geo.imagery against small synthetic NZTM aerials."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

from button_nz.geo.imagery import read_aerial

rio: Any = rasterio  # no type stubs
LEFT, TOP = 1000.0, 2000.0  # NZTM of the image's top-left corner


def _write(
    path: Path,
    rgb: NDArray[np.uint8],
    crs: int = 2193,
    pixel_m: float = 0.5,
    left: float = LEFT,
) -> str:
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "height": rgb.shape[1],
        "width": rgb.shape[2],
        "count": rgb.shape[0],
        "dtype": "uint8",
        "crs": f"EPSG:{crs}",
        "transform": rio.transform.from_origin(left, TOP, pixel_m, pixel_m),
    }
    with rio.open(path, "w", **profile) as dst:
        dst.write(rgb)
    return str(path)


@pytest.fixture
def aerial(tmp_path: Path) -> str:
    """100 m square at 0.5 m: red in the west half, blue in the east."""
    rgb = np.zeros((3, 200, 200), dtype=np.uint8)
    rgb[0, :, :100] = 200
    rgb[2, :, 100:] = 200
    return _write(tmp_path / "aerial.tif", rgb)


def test_reads_a_bbox_at_the_requested_pixel_size(aerial: str) -> None:
    image = read_aerial([aerial], (1040.0, 1940.0, 1060.0, 1960.0), pixel_m=0.25)
    assert image.shape == (80, 80, 3)
    assert image.dtype == np.uint8
    assert tuple(image[40, 10]) == (200, 0, 0)  # west of x = 1050: red
    assert tuple(image[40, 70]) == (0, 0, 200)  # east: blue


def test_rows_run_north_to_south(tmp_path: Path) -> None:
    rgb = np.zeros((3, 200, 200), dtype=np.uint8)
    rgb[1, :100, :] = 250  # the north half is green
    path = _write(tmp_path / "ns.tif", rgb)
    image = read_aerial([path], (1000.0, 1900.0, 1100.0, 2000.0), pixel_m=1.0)
    assert image[0, 50, 1] == 250 and image[-1, 50, 1] == 0


def test_a_bbox_beyond_the_image_raises(aerial: str) -> None:
    with pytest.raises(ValueError, match="not covered"):
        read_aerial([aerial], (1090.0, 1940.0, 1110.0, 1960.0), pixel_m=0.25)


def test_a_non_nztm_image_raises(tmp_path: Path) -> None:
    path = _write(tmp_path / "wgs.tif", np.zeros((3, 10, 10), dtype=np.uint8), crs=4326)
    with pytest.raises(ValueError, match="EPSG:2193"):
        read_aerial([path], (1000.0, 1995.0, 1005.0, 2000.0), pixel_m=1.0)


def test_an_image_without_three_bands_raises(tmp_path: Path) -> None:
    path = _write(tmp_path / "grey.tif", np.zeros((1, 10, 10), dtype=np.uint8))
    with pytest.raises(ValueError, match="RGB"):
        read_aerial([path], (1000.0, 1995.0, 1005.0, 2000.0), pixel_m=1.0)


def test_neighbouring_tiles_are_joined(tmp_path: Path) -> None:
    west = np.full((3, 200, 200), 50, dtype=np.uint8)
    east = np.full((3, 200, 200), 150, dtype=np.uint8)
    tiles = [
        _write(tmp_path / "west.tif", west),
        _write(tmp_path / "east.tif", east, left=LEFT + 100.0),
    ]
    image = read_aerial(tiles, (1090.0, 1950.0, 1110.0, 1960.0), pixel_m=0.5)
    assert image.shape == (20, 40, 3)
    assert image[:, :20].max() == 50 and image[:, 20:].min() == 150  # no gap, no blend


def test_a_bbox_only_partly_covered_by_the_tiles_raises(aerial: str) -> None:
    with pytest.raises(ValueError, match="not covered"):
        read_aerial([aerial], (1090.0, 1950.0, 1110.0, 1960.0), pixel_m=0.5)
