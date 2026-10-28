"""Tests for button_nz.perception.features: segmentation masks as georeferenced
site features, cross-checked against the LiDAR."""

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.features import Mask, Status, features, unlabelled

PIXEL_M = 0.25  # 4 px per 1 m cell
BBOX = (1000.0, 2000.0, 1040.0, 2030.0)  # 40 m x 30 m


def grid(ndsm: NDArray[np.float64] | None = None) -> TerrainGrid:
    dem = np.full((30, 40), 100.0)
    above = np.zeros_like(dem) if ndsm is None else ndsm
    return TerrainGrid(BBOX, 1.0, dem, above, ("synthetic",))


def mask(concept: str, rows: slice, cols: slice, score: float = 0.9) -> Mask:
    """A mask on the 0.25 m crop; rows and cols are in metres from the north-west."""
    pixels = np.zeros((120, 160), dtype=bool)
    pixels[rows.start * 4 : rows.stop * 4, cols.start * 4 : cols.stop * 4] = True
    return Mask(concept, score, pixels)


SHED_HEIGHT = np.zeros((30, 40))
SHED_HEIGHT[5:9, 10:16] = 2.6  # a 6 m x 4 m shed, 2.6 m tall


def test_a_mask_becomes_an_nztm_polygon() -> None:
    (feature,) = features(
        [mask("shed", slice(5, 9), slice(10, 16))], grid(SHED_HEIGHT), BBOX, PIXEL_M
    )
    west, south, east, north = feature.polygon.bounds
    assert (west, south, east, north) == pytest.approx((1010.0, 2021.0, 1016.0, 2025.0))
    assert feature.area_m2 == pytest.approx(24.0)


def test_a_labelled_structure_with_height_agrees() -> None:
    (feature,) = features(
        [mask("shed", slice(5, 9), slice(10, 16))], grid(SHED_HEIGHT), BBOX, PIXEL_M
    )
    assert feature.status is Status.AGREES
    assert feature.max_height_m == pytest.approx(2.6)


def test_a_structure_the_lidar_sees_no_height_in_conflicts() -> None:
    (feature,) = features(
        [mask("shed", slice(20, 24), slice(10, 16))], grid(SHED_HEIGHT), BBOX, PIXEL_M
    )
    assert feature.status is Status.CONFLICT
    assert "LiDAR" in feature.note


def test_ground_with_something_standing_on_it_conflicts() -> None:
    (feature,) = features(
        [mask("driveway", slice(5, 9), slice(10, 16))], grid(SHED_HEIGHT), BBOX, PIXEL_M
    )
    assert feature.status is Status.CONFLICT


def test_vehicles_are_transient() -> None:
    (feature,) = features(
        [mask("vehicle", slice(5, 9), slice(10, 16))], grid(SHED_HEIGHT), BBOX, PIXEL_M
    )
    assert feature.status is Status.TRANSIENT


def test_raised_ground_nothing_labelled_is_reported() -> None:
    other = SHED_HEIGHT.copy()
    other[20:25, 30:35] = 4.0  # a 5 m x 5 m something nobody labelled
    labelled = features([mask("shed", slice(5, 9), slice(10, 16))], grid(other), BBOX, PIXEL_M)
    (found,) = unlabelled(labelled, grid(other), BBOX)
    assert found.status is Status.UNLABELLED
    assert found.polygon.bounds == pytest.approx((1030.0, 2005.0, 1035.0, 2010.0))
    assert found.max_height_m == pytest.approx(4.0)


def test_a_mask_that_does_not_match_the_crop_raises() -> None:
    wrong = Mask("shed", 0.9, np.zeros((10, 10), dtype=bool))
    with pytest.raises(ValueError, match="crop"):
        features([wrong], grid(), BBOX, PIXEL_M)


def test_raised_ground_outside_the_crop_is_not_reported() -> None:
    """The LiDAR grid is read with a margin; no mask could label what's outside the crop."""
    other = SHED_HEIGHT.copy()
    other[20:25, 30:35] = 4.0
    crop = (1000.0, 2000.0, 1025.0, 2030.0)  # stops short of the block at x 1030-1035
    (shed,) = unlabelled([], grid(other), crop)  # only the shed, inside the crop
    assert shed.polygon.bounds == pytest.approx((1010.0, 2021.0, 1016.0, 2025.0))


def test_the_unlabelled_part_of_a_raised_area_is_reported() -> None:
    """A shed with an unlabelled lean-to: the lean-to is reported, the shed isn't."""
    other = SHED_HEIGHT.copy()
    other[5:9, 16:21] = 2.5  # a 5 m x 4 m lean-to joined to the shed's east wall
    labelled = features([mask("shed", slice(5, 9), slice(10, 16))], grid(other), BBOX, PIXEL_M)
    (found,) = unlabelled(labelled, grid(other), BBOX)
    assert found.polygon.bounds == pytest.approx((1016.0, 2021.0, 1021.0, 2025.0), abs=0.3)
    assert found.area_m2 == pytest.approx(20.0, abs=2.0)


def test_a_crop_the_lidar_doesnt_cover_raises() -> None:
    beyond = (990.0, 2000.0, 1030.0, 2030.0)  # 10 m west of the grid
    pixels = np.zeros((120, 160), dtype=bool)
    with pytest.raises(ValueError, match="LiDAR"):
        features([Mask("shed", 0.9, pixels)], grid(), beyond, PIXEL_M)
