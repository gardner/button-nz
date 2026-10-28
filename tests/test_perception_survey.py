"""Tests for button_nz.perception.survey: every concept asked, checked against
the LiDAR, and kept as GeoJSON."""

import json

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.features import Mask, Status
from button_nz.perception.survey import CONCEPTS, survey, to_geojson

PIXEL_M = 0.25  # 4 px per 1 m cell
BBOX = (1000.0, 2000.0, 1040.0, 2030.0)  # 40 m x 30 m
HEIGHTS = np.zeros((30, 40))
HEIGHTS[5:9, 10:16] = 2.6  # a 6 m x 4 m shed, 2.6 m tall
HEIGHTS[20:23, 30:33] = 3.0  # 9 m² standing up that nothing labels
GRID = TerrainGrid(BBOX, 1.0, np.full((30, 40), 100.0), HEIGHTS, ("synthetic",))


def shed_only(rgb: NDArray[np.uint8], concept: str) -> list[Mask]:
    if concept != "shed":
        return []
    pixels = np.zeros(rgb.shape[:2], dtype=bool)
    pixels[5 * 4 : 9 * 4, 10 * 4 : 16 * 4] = True
    return [Mask("shed", 0.8, pixels)]


AERIAL = np.zeros((120, 160, 3), dtype=np.uint8)


def test_every_concept_is_asked_once() -> None:
    asked: list[str] = []

    def segment(rgb: NDArray[np.uint8], concept: str) -> list[Mask]:
        asked.append(concept)
        return []

    survey(segment, AERIAL, GRID, BBOX, PIXEL_M)
    assert asked == list(CONCEPTS)
    assert all("," not in concept for concept in CONCEPTS)  # SAM takes one at a time


def test_labelled_features_are_checked_and_raised_ground_nobody_labelled_is_added() -> None:
    shed, other = survey(shed_only, AERIAL, GRID, BBOX, PIXEL_M)
    assert shed.concept == "shed" and shed.status is Status.AGREES
    assert other.status is Status.UNLABELLED and other.area_m2 == pytest.approx(9.0)


def test_the_geojson_says_what_each_feature_is_and_where() -> None:
    found = survey(shed_only, AERIAL, GRID, BBOX, PIXEL_M)
    collection = json.loads(json.dumps(to_geojson(found, {"model": "sam-3.1"})))
    assert collection["type"] == "FeatureCollection" and collection["model"] == "sam-3.1"
    assert collection["crs"] == "EPSG:2193"
    shed, other = collection["features"]
    assert shed["id"] == "1" and other["id"] == "2"
    assert shed["properties"] == {
        "concept": "shed",
        "score": 0.8,
        "area_m2": pytest.approx(24.0),
        "max_height_m": pytest.approx(2.6),
        "status": "agrees",
        "note": shed["properties"]["note"],
    }
    assert shed["geometry"]["type"] == "Polygon"
    xs = [x for x, _ in shed["geometry"]["coordinates"][0]]
    assert (min(xs), max(xs)) == (1010.0, 1016.0)  # NZTM metres
    assert other["properties"]["score"] is None
