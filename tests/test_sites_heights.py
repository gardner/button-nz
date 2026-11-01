"""Tests for button_nz.sites.heights: what the LiDAR says stands where."""

import numpy as np
import pytest
from numpy.typing import NDArray
from shapely import Polygon, box

from button_nz.geo.terrain import TerrainGrid
from button_nz.sites.heights import canopy, height_above, median_ground

# 20 m x 20 m of 1 m cells from (0, 0); ground 100 m rising 0.1 m per metre east.
xs = np.arange(20) + 0.5
DEM: NDArray[np.float64] = np.tile(100.0 + 0.1 * xs, (20, 1)).astype(np.float64)


def grid(ndsm: NDArray[np.float64]) -> TerrainGrid:
    return TerrainGrid((0.0, 0.0, 20.0, 20.0), 1.0, DEM, ndsm, ("synthetic",))


def with_block(height: float, west: int, south: int, east: int, north: int) -> NDArray[np.float64]:
    """An nDSM of 0 with ``height`` over the cells of the box (rows count from the north)."""
    ndsm = np.zeros((20, 20))
    ndsm[20 - north : 20 - south, west:east] = height
    return ndsm


def test_a_buildings_height_is_the_90th_percentile_of_the_ndsm_over_it() -> None:
    ndsm = with_block(4.0, 2, 2, 8, 8)
    ndsm[13, 2:5] = 9.0  # three cells of chimney (8%): the 90th percentile is the roof
    assert height_above(grid(ndsm), box(2, 2, 8, 8)) == pytest.approx(4.0)


def test_somewhere_with_no_whole_cell_has_no_height() -> None:
    assert height_above(grid(np.zeros((20, 20))), box(2.2, 2.2, 2.4, 2.4)) is None
    assert height_above(grid(np.zeros((20, 20))), box(50, 50, 60, 60)) is None


def test_the_ground_under_somewhere_is_the_median_dem() -> None:
    assert median_ground(grid(np.zeros((20, 20))), box(0, 0, 10, 4)) == pytest.approx(100.5)


def test_canopy_is_what_stands_over_2_m_outside_the_buildings_with_its_height() -> None:
    ndsm = with_block(6.0, 2, 2, 8, 8) + with_block(12.0, 12, 12, 18, 18)
    trees = canopy(grid(ndsm), [box(2, 2, 8, 8)])  # the first block is a building
    assert len(trees) == 1
    tree, height = trees[0]
    assert tree.area == pytest.approx(36.0, rel=0.05)
    assert tree.intersects(Polygon([(13, 13), (17, 13), (17, 17)]))
    assert height == pytest.approx(12.0)


def test_low_planting_and_specks_are_not_canopy() -> None:
    ndsm = with_block(1.5, 0, 0, 10, 10) + with_block(5.0, 15, 15, 16, 16)  # 1 m² of 5 m
    assert canopy(grid(ndsm), []) == []
