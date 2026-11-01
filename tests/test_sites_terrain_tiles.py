"""Tests for button_nz.sites.terrain_tiles: the site's surface as terrain-RGB."""

import io
import math

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image
from pyproj import Transformer

from button_nz.geo.terrain import TerrainGrid
from button_nz.sites.terrain_tiles import decode, encode, terrain_tile

TO_LONLAT = Transformer.from_crs(2193, 4326, always_xy=True)
# 100 m x 100 m of 1 m cells at Reefton; ground 190 m, a 6 m house in the middle.
LEFT, BOTTOM = 1505900.0, 5336750.0
DEM: NDArray[np.float64] = np.full((100, 100), 190.0)
NDSM: NDArray[np.float64] = np.zeros((100, 100))
NDSM[45:55, 45:55] = 6.0
GRID = TerrainGrid((LEFT, BOTTOM, LEFT + 100, BOTTOM + 100), 1.0, DEM, NDSM, ("synthetic",))
DATUM = 190.0


def tile_at(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def heights(png: bytes) -> NDArray[np.float64]:
    with Image.open(io.BytesIO(png)) as image:
        return decode(np.asarray(image.convert("RGB")))


def test_terrain_rgb_round_trips_to_a_tenth_of_a_metre() -> None:
    values = np.array([[0.0, 6.0, -3.4, 1234.5]])
    assert decode(encode(values)) == pytest.approx(values, abs=0.05)


def test_a_tile_over_the_site_is_its_surface_above_the_datum() -> None:
    lon, lat = TO_LONLAT.transform(LEFT + 50, BOTTOM + 50)  # the house
    x, y = tile_at(lon, lat, 20)
    png = terrain_tile(GRID, DATUM, 20, x, y)
    assert png is not None
    found = heights(png)
    assert found.shape == (256, 256)
    assert found.max() == pytest.approx(6.0, abs=0.05)  # the roof, above the ground
    assert found.min() == pytest.approx(0.0, abs=0.05)  # the ground, at the datum


def test_a_tile_off_the_site_or_out_of_zoom_is_none() -> None:
    lon, lat = TO_LONLAT.transform(LEFT + 50, BOTTOM + 50)
    x, y = tile_at(lon, lat, 18)
    assert terrain_tile(GRID, DATUM, 18, x + 20, y) is None  # kilometres away
    assert terrain_tile(GRID, DATUM, 14, *tile_at(lon, lat, 14)) is None
    assert terrain_tile(GRID, DATUM, 21, *tile_at(lon, lat, 21)) is None
