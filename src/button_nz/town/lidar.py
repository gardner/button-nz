"""What the LiDAR shows standing on a town's sections today.

LINZ's building outlines can be years older than the LiDAR, so the screen
also keeps clear of every cell whose nDSM (surface minus ground) is over
``TALL_M``: buildings, trees, hedges and anything else that tall. The town's
DEM and DSM tiles are joined into one local raster each (``mosaic``), which
``geo.terrain.read_terrain`` then reads like a site's.
"""

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from rasterio import merge as rio_merge  # pyright: ignore[reportMissingTypeStubs]
from shapely import Polygon, box, union_all
from shapely.geometry.base import BaseGeometry

from button_nz.geo.geometry import BBox
from button_nz.geo.terrain import TerrainGrid, read_terrain
from button_nz.geo.tiles import tiles_covering

TALL_M = 2.0
LIDAR_TILE_SCALE = 10000  # the West Coast 1 m DEM and DSM are 1:10,000 tiles
WEST_COAST_LIDAR = (
    "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022"
)

rio: Any = rasterio  # untyped, as in geo.terrain
merging: Any = rio_merge  # untyped too


def tile_urls(bbox: BBox, kind: str, base: str = WEST_COAST_LIDAR) -> list[str]:
    """The ``kind`` (``dem_1m`` or ``dsm_1m``) tiles covering ``bbox``."""
    return [f"{base}/{kind}/2193/{name}.tiff" for name in tiles_covering(bbox, LIDAR_TILE_SCALE)]


def mosaic(urls: Sequence[str], bbox: BBox, path: Path) -> Path:
    """Join the tiles at ``urls`` into one GeoTIFF covering ``bbox`` exactly,
    keeping their grid and nodata (never filled in)."""
    sources = [rio.open(url) for url in urls]
    try:
        first = sources[0]
        cells, transform = merging.merge(sources, bounds=bbox, nodata=first.nodata)
        profile = {
            "driver": "GTiff",
            "dtype": cells.dtype,
            "width": cells.shape[2],
            "height": cells.shape[1],
            "count": 1,
            "crs": first.crs,
            "transform": transform,
            "nodata": first.nodata,
            "compress": "deflate",
        }
        with rio.open(path, "w", **profile) as out:
            out.write(cells)
    finally:
        for source in sources:
            source.close()
    return path


def west_coast_lidar(cache: Path) -> Callable[[BBox], TerrainGrid]:
    """The West Coast DEM and nDSM over a whole-metre bbox, the screen's own
    tiles joined into ``cache`` (one at a time: each read replaces the last)."""

    def read(bbox: BBox) -> TerrainGrid:
        cache.mkdir(parents=True, exist_ok=True)
        dem = mosaic(tile_urls(bbox, "dem_1m"), bbox, cache / "dem.tif")
        dsm = mosaic(tile_urls(bbox, "dsm_1m"), bbox, cache / "dsm.tif")
        return read_terrain(str(dem), str(dsm), bbox, margin_m=0.0)

    return read


def tall_cells(grid: TerrainGrid, bounds: BBox, threshold: float = TALL_M) -> BaseGeometry:
    """The cells of ``grid`` touching ``bounds`` whose nDSM is over
    ``threshold``, as NZTM squares. Raises ``ValueError`` if ``bounds`` reaches
    outside the grid."""
    left, _, _, top = grid.bbox
    cell = grid.cell_m
    col0 = math.floor(round((bounds[0] - left) / cell, 9))
    col1 = math.ceil(round((bounds[2] - left) / cell, 9))
    row0 = math.floor(round((top - bounds[3]) / cell, 9))
    row1 = math.ceil(round((top - bounds[1]) / cell, 9))
    rows, cols = grid.ndsm.shape
    if col0 < 0 or row0 < 0 or col1 > cols or row1 > rows:
        raise ValueError(f"{bounds} reaches outside the LiDAR grid {grid.bbox}")
    window = grid.ndsm[row0:row1, col0:col1]
    squares: list[Polygon] = []
    for r, c in np.argwhere(window > threshold):
        x = left + (col0 + int(c)) * cell
        y = top - (row0 + int(r)) * cell
        squares.append(box(x, y - cell, x + cell, y))
    return union_all(squares) if squares else Polygon()
