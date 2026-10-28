"""Tests for button_nz.geo.terrain against small synthetic NZTM rasters."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

from button_nz.geo.terrain import read_terrain

rio: Any = rasterio  # no type stubs

LEFT, TOP = 1000.0, 2000.0  # NZTM of the rasters' top-left corner
SIZE = 100  # 100 x 100 cells of 1 m


def _write(path: Path, data: NDArray[np.float32], crs: int = 2193, left: float = LEFT) -> str:
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": f"EPSG:{crs}",
        "transform": rio.transform.from_origin(left, TOP, 1.0, 1.0),
        "nodata": -9999.0,
    }
    with rio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return str(path)


@pytest.fixture
def ground() -> NDArray[np.float32]:
    """Ground rising 0.1 m per metre east, from 100 m."""
    cols = np.arange(SIZE, dtype=np.float32)
    return np.tile(100.0 + 0.1 * cols, (SIZE, 1)).astype(np.float32)


@pytest.fixture
def rasters(tmp_path: Path, ground: NDArray[np.float32]) -> tuple[str, str]:
    surface = ground.copy()
    surface[40:45, 50:55] += 6.0  # a 5 x 5 m structure, 6 m tall
    return _write(tmp_path / "dem.tif", ground), _write(tmp_path / "dsm.tif", surface)


EXTENT = (1040.0, 1940.0, 1060.0, 1960.0)  # a 20 m square site


def test_reads_the_extent_plus_margin_snapped_to_cells(rasters: tuple[str, str]) -> None:
    grid = read_terrain(*rasters, EXTENT, margin_m=5.0)
    assert grid.bbox == (1035.0, 1935.0, 1065.0, 1965.0)
    assert grid.cell_m == 1.0
    assert grid.dem.shape == (30, 30)
    assert grid.ndsm.shape == (30, 30)


def test_partial_cells_round_outwards(rasters: tuple[str, str]) -> None:
    grid = read_terrain(*rasters, (1040.4, 1940.6, 1059.5, 1959.2), margin_m=0.0)
    assert grid.bbox == (1040.0, 1940.0, 1060.0, 1960.0)


def test_row_zero_is_north_and_heights_are_the_dem(rasters: tuple[str, str]) -> None:
    grid = read_terrain(*rasters, EXTENT, margin_m=0.0)
    assert grid.dem[0, 0] == pytest.approx(100.0 + 0.1 * 40)
    assert grid.dem[0, -1] == pytest.approx(100.0 + 0.1 * 59)


def test_ndsm_is_dsm_minus_dem(rasters: tuple[str, str]) -> None:
    grid = read_terrain(*rasters, EXTENT, margin_m=0.0)
    # The structure covers rows 40-44 and cols 50-54 of the raster; the window
    # starts at row 40 (y 1960) and col 40 (x 1040).
    assert grid.ndsm[0:5, 10:15] == pytest.approx(np.full((5, 5), 6.0))
    assert float(grid.ndsm.sum()) == pytest.approx(25 * 6.0)


def test_nodata_in_the_window_raises(
    tmp_path: Path, ground: NDArray[np.float32], rasters: tuple[str, str]
) -> None:
    holed = ground.copy()
    holed[45, 45] = -9999.0
    dem = _write(tmp_path / "holed.tif", holed)
    with pytest.raises(ValueError, match="nodata"):
        read_terrain(dem, rasters[1], EXTENT, margin_m=0.0)


def test_misaligned_rasters_raise(
    tmp_path: Path, ground: NDArray[np.float32], rasters: tuple[str, str]
) -> None:
    shifted = _write(tmp_path / "shifted.tif", ground, left=LEFT + 0.5)
    with pytest.raises(ValueError, match="grid"):
        read_terrain(rasters[0], shifted, EXTENT, margin_m=0.0)


def test_a_non_nztm_raster_raises(tmp_path: Path, ground: NDArray[np.float32]) -> None:
    dem = _write(tmp_path / "web.tif", ground, crs=3857)
    with pytest.raises(ValueError, match="2193"):
        read_terrain(dem, dem, EXTENT, margin_m=0.0)


def test_an_extent_outside_the_raster_raises(rasters: tuple[str, str]) -> None:
    with pytest.raises(ValueError, match="outside"):
        read_terrain(*rasters, (900.0, 1940.0, 920.0, 1960.0), margin_m=0.0)
