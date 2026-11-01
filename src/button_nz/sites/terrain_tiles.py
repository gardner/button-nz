"""A site's surface (the DSM) as terrain-RGB tiles, for a web map's 3D terrain.

Each WebMercatorQuad tile at zooms ``MIN_ZOOM``-``MAX_ZOOM`` that touches the
site's LiDAR grid is 256 x 256 pixels of the DSM's height above the site's
datum (its scene's ``datum_m``), Mapbox-encoded: height = -10000 + 0.1 x
(R x 65536 + G x 256 + B). Heights are above the datum, not sea level, so the
site meets a web map's flat 0 m at its edge; a pixel beyond the grid is 0
there too, as a map draws a missing tile. A tile that touches no part of the
grid is None (a 404).
"""

import io
import math

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from pyproj import Transformer

from button_nz.geo.lonlat import TO_LONLAT
from button_nz.geo.terrain import TerrainGrid

MIN_ZOOM, MAX_ZOOM = 15, 20
SIZE = 256
TO_NZTM = Transformer.from_crs(4326, 2193, always_xy=True)


def encode(heights: NDArray[np.float64]) -> NDArray[np.uint8]:
    value = np.round((heights + 10000.0) * 10.0).astype(np.int64)
    rgb = np.stack([value // 65536, (value // 256) % 256, value % 256], axis=-1)
    return rgb.astype(np.uint8)


def decode(rgb: NDArray[np.uint8]) -> NDArray[np.float64]:
    r, g, b = (rgb[..., k].astype(np.float64) for k in range(3))
    return -10000.0 + (r * 65536 + g * 256 + b) * 0.1


def terrain_tile(grid: TerrainGrid, datum_m: float, z: int, x: int, y: int) -> bytes | None:
    if not MIN_ZOOM <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
        return None
    if not _touches(grid, z, x, y):
        return None
    steps = (np.arange(SIZE) + 0.5) / SIZE
    lon = (x + steps) / 2**z * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + steps) / 2**z))))
    lons = np.broadcast_to(lon[np.newaxis, :], (SIZE, SIZE))  # each row, west to east
    lats = np.broadcast_to(lat[:, np.newaxis], (SIZE, SIZE))  # each column, north to south
    east, north = TO_NZTM.transform(lons, lats)
    left, _, _, top = grid.bbox
    col = np.floor((east - left) / grid.cell_m).astype(np.int64)
    row = np.floor((top - north) / grid.cell_m).astype(np.int64)
    rows, cols = grid.dem.shape
    inside = (row >= 0) & (row < rows) & (col >= 0) & (col < cols)
    surface = grid.dem + grid.ndsm
    heights = np.zeros((SIZE, SIZE))
    heights[inside] = surface[row[inside], col[inside]] - datum_m
    buffer = io.BytesIO()
    Image.fromarray(encode(heights), "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _touches(grid: TerrainGrid, z: int, x: int, y: int) -> bool:
    west, south, east, north = TO_LONLAT.transform_bounds(*grid.bbox)
    n = 2**z
    tile_west, tile_east = x / n * 360.0 - 180.0, (x + 1) / n * 360.0 - 180.0
    tile_north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    tile_south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return tile_west < east and west < tile_east and tile_south < north and south < tile_north
