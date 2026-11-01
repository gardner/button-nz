"""Every extrudable layer of a site map shares one convention: ``base_m`` is the
bottom and ``height_m`` the top, both above the site's datum, as the design map
gives its walls; ``above_ground_m`` is the height above its own ground."""

import numpy as np
from shapely import box

from button_nz.geo.terrain import TerrainGrid
from button_nz.sites.layers import Lidar, building_heights, canopy_layer, extrusion

# 20 m x 20 m at 1 m, ground 3 m above a datum of 100 m, a 4.5 m house on 8-12 x 8-12.
DEM = np.full((20, 20), 103.0)
NDSM = np.zeros((20, 20))
NDSM[8:12, 8:12] = 4.5
LIDAR = Lidar(TerrainGrid((0.0, 0.0, 20.0, 20.0), 1.0, DEM, NDSM, ("synthetic",)), 100.0)
HOUSE = box(8.0, 8.0, 12.0, 12.0)


def test_a_building_stands_on_its_ground_and_reaches_its_top_above_the_datum() -> None:
    assert building_heights(HOUSE, LIDAR) == {"base_m": 3.0, "height_m": 7.5, "above_ground_m": 4.5}


def test_beyond_the_lidar_nothing_is_guessed() -> None:
    far = box(50.0, 50.0, 54.0, 54.0)
    unknown = {"base_m": None, "height_m": None, "above_ground_m": None}
    assert building_heights(far, LIDAR) == unknown


def test_a_known_height_on_ground_stands_on_that_ground() -> None:
    assert extrusion(HOUSE, LIDAR, 6.9) == {"base_m": 3.0, "height_m": 9.9, "above_ground_m": 6.9}


def test_a_building_the_owner_confirmed_is_not_also_canopy() -> None:
    assert len(canopy_layer([], [], LIDAR)["features"]) == 1  # unknown, it stands up as canopy
    assert canopy_layer([], [HOUSE], LIDAR)["features"] == []  # confirmed, it's a building
