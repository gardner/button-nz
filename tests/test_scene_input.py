"""Tests for button_nz.blender_worker.scene_input."""

import json

import numpy as np
import pytest

from button_nz.blender_worker.scene_input import scene_input
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import TerrainGrid


@pytest.fixture
def grid() -> TerrainGrid:
    dem = np.array([[10.0, 11.0, 12.0], [10.5, 11.5, 12.5]])
    ndsm = np.array([[0.0, 3.0, 0.0], [0.0, 0.0, 0.1]])
    return TerrainGrid(
        bbox=(100.0, 200.0, 103.0, 202.0),
        cell_m=1.0,
        dem=dem,
        ndsm=ndsm,
        sources=("dem.tif", "dsm.tif"),
    )


def test_vertices_are_cell_centres_in_the_local_frame(grid: TerrainGrid) -> None:
    scene = scene_input(grid, LocalFrame(origin=(101.0, 201.0)), parcels=[])
    terrain = scene["terrain"]
    assert (terrain["rows"], terrain["cols"], terrain["cell_m"]) == (2, 3, 1.0)
    # Top-left cell centre is (100.5, 201.5) in NZTM, (-0.5, 0.5) locally.
    assert (terrain["x0"], terrain["y0"]) == (-0.5, 0.5)


def test_heights_are_row_major_relative_to_the_datum(grid: TerrainGrid) -> None:
    scene = scene_input(grid, LocalFrame(origin=(101.0, 201.0)), parcels=[])
    assert scene["frame"]["datum_m"] == 10.0
    assert scene["terrain"]["heights"] == pytest.approx([0.0, 1.0, 2.0, 0.5, 1.5, 2.5])
    assert scene["ndsm"]["heights"] == pytest.approx([0.0, 3.0, 0.0, 0.0, 0.0, 0.1])


def test_an_explicit_datum_is_kept(grid: TerrainGrid) -> None:
    scene = scene_input(grid, LocalFrame(origin=(101.0, 201.0)), parcels=[], datum_m=0.0)
    assert scene["frame"]["datum_m"] == 0.0
    assert scene["terrain"]["heights"][0] == 10.0


def test_parcels_are_in_the_local_frame(grid: TerrainGrid) -> None:
    ring = ((100.0, 200.0), (102.0, 200.0), (102.0, 202.0), (100.0, 200.0))
    scene = scene_input(grid, LocalFrame(origin=(101.0, 201.0)), parcels=[ring])
    assert scene["parcels"] == [[[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, -1.0]]]


def test_the_scene_is_plain_json(grid: TerrainGrid) -> None:
    scene = scene_input(grid, LocalFrame(origin=(101.0, 201.0)), parcels=[])
    assert json.loads(json.dumps(scene)) == scene
    assert scene["frame"]["origin_nztm"] == [101.0, 201.0]
    assert scene["frame"]["crs"] == "EPSG:2193"
    assert scene["frame"]["vertical_crs"] == "EPSG:7839"
    assert scene["sources"] == ["dem.tif", "dsm.tif"]
