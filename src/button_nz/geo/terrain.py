"""Measured terrain for a site: DEM ground heights and the above-ground
surface (nDSM = DSM - DEM) on the DEM's own 1 m grid, in NZTM2000/NZVD2016.

The nDSM is evidence of something above ground, not an exact building or tree
height: it carries the sampling, registration and capture-date limits of the
LiDAR. Nodata is never filled in; a window containing any raises.
"""

import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

from button_nz.geo.geometry import BBox

NZTM = 2193

# rasterio has no type stubs: it and its handles are typed Any here, and
# everything read from them is converted to plain floats or typed arrays at once.
type Raster = Any
rio: Any = rasterio


@dataclass(frozen=True, eq=False)
class TerrainGrid:
    """Cells of ``cell_m`` metres covering ``bbox``; row 0 is the north edge."""

    bbox: BBox
    cell_m: float
    dem: NDArray[np.float64]
    ndsm: NDArray[np.float64]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class _Grid:
    left: float
    top: float
    cell: float
    width: int
    height: int


def read_terrain(dem_path: str, dsm_path: str, extent: BBox, margin_m: float = 20.0) -> TerrainGrid:
    """Read the DEM and DSM cells covering ``extent`` plus ``margin_m``, rounded
    outwards to whole cells. Paths may be local files or URLs to COGs."""
    dem: Raster
    dsm: Raster
    with rio.open(dem_path) as dem, rio.open(dsm_path) as dsm:
        grid = _check_grids(dem, dsm)
        col0, row0, col1, row1 = _cells(grid, extent, margin_m)
        window: Any = rio.windows.Window(col0, row0, col1 - col0, row1 - row0)
        ground = _read(dem, window, "DEM")
        surface = _read(dsm, window, "DSM")
    bbox = (
        grid.left + col0 * grid.cell,
        grid.top - row1 * grid.cell,
        grid.left + col1 * grid.cell,
        grid.top - row0 * grid.cell,
    )
    return TerrainGrid(bbox, grid.cell, ground, surface - ground, (dem_path, dsm_path))


def _check_grids(dem: Raster, dsm: Raster) -> _Grid:
    for name, src in (("DEM", dem), ("DSM", dsm)):
        epsg = cast("int | None", src.crs.to_epsg()) if src.crs else None
        if epsg != NZTM:
            raise ValueError(f"{name} must be in EPSG:{NZTM}, not {src.crs}")
    a, b, c, d, e, f = (float(v) for v in cast("tuple[float, ...]", tuple(dem.transform)[:6]))
    if tuple(dem.transform)[:6] != tuple(dsm.transform)[:6]:
        raise ValueError("DEM and DSM are not on the same grid")
    if a != -e or b or d:
        raise ValueError("DEM grid cells must be square and north-up")
    return _Grid(left=c, top=f, cell=a, width=int(dem.width), height=int(dem.height))


def _cells(grid: _Grid, extent: BBox, margin_m: float) -> tuple[int, int, int, int]:
    """Column and row bounds (col0, row0, col1, row1) of the window."""

    def cells(distance: float) -> float:
        return round(distance / grid.cell, 9)  # absorb float noise before rounding

    col0 = math.floor(cells(extent[0] - margin_m - grid.left))
    col1 = math.ceil(cells(extent[2] + margin_m - grid.left))
    row0 = math.floor(cells(grid.top - (extent[3] + margin_m)))
    row1 = math.ceil(cells(grid.top - (extent[1] - margin_m)))
    if col0 < 0 or row0 < 0 or col1 > grid.width or row1 > grid.height:
        raise ValueError(f"extent {extent} plus {margin_m} m margin is outside the raster")
    return col0, row0, col1, row1


def _read(src: Raster, window: Any, name: str) -> NDArray[np.float64]:
    cells = cast("NDArray[np.float64]", src.read(1, window=window)).astype(np.float64)
    # GDAL's mask covers the nodata value, internal masks and alpha bands.
    valid = cast("NDArray[np.uint8]", src.read_masks(1, window=window))
    missing: NDArray[np.bool_] = np.isnan(cells) | (valid == 0)
    nodata = cast("float | None", src.nodata)
    if nodata is not None:
        missing |= cells == nodata
    if bool(missing.any()):
        raise ValueError(f"{name} has {int(missing.sum())} nodata cells in the window")
    return cells
