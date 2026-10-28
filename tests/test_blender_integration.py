"""Real headless Blender runs. Excluded by default (no Blender or GPU in CI);
run with `pytest -m blender`. The demo-site test also downloads the DEM/DSM
windows from LINZ's public S3."""

import json
import struct
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from button_nz.blender_worker.demo import build_demo_scene
from button_nz.blender_worker.run import build_scene
from button_nz.blender_worker.scene_input import scene_input
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender


def _gltf(glb: Path) -> dict[str, Any]:
    """The JSON chunk of a GLB file."""
    data = glb.read_bytes()
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF"
    chunk_length, chunk_type = struct.unpack_from("<I4s", data, 12)
    assert chunk_type == b"JSON"
    gltf: dict[str, Any] = json.loads(data[20 : 20 + chunk_length])
    return gltf


def _bounds(gltf: dict[str, Any], node_name: str) -> tuple[list[float], list[float]]:
    """POSITION min/max of a node's mesh, in glTF's Y-up axes (x, z, -y)."""
    node = next(n for n in gltf["nodes"] if n["name"] == node_name)
    primitive = gltf["meshes"][node["mesh"]]["primitives"][0]
    accessor = gltf["accessors"][primitive["attributes"]["POSITION"]]
    return accessor["min"], accessor["max"]


def test_builds_a_metric_scene(tmp_path: Path) -> None:
    dem = np.tile(np.linspace(10.0, 14.9, 50), (40, 1))  # 50 m x 40 m, rising 5 m east
    ndsm = np.zeros_like(dem)
    ndsm[10:15, 20:25] = 6.0  # a 5 m x 5 m, 6 m tall structure
    grid = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, dem, ndsm, ("synthetic",))
    ring = ((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0))
    scene = scene_input(grid, LocalFrame.centred_on(grid.bbox), [ring])

    out = build_scene(scene, tmp_path)

    gltf = _gltf(out.glb)
    names = {n["name"] for n in gltf["nodes"]}
    assert {"Terrain", "AboveGround", "Parcel.0"} <= names
    low, high = _bounds(gltf, "Terrain")
    assert low[0] == pytest.approx(-24.5) and high[0] == pytest.approx(24.5)  # east-west
    assert low[1] == pytest.approx(0.0) and high[1] == pytest.approx(4.9)  # height above datum
    _, column_top = _bounds(gltf, "AboveGround")
    # The column stands on cols 20-24, where ground is 12.0-12.4 m, i.e. 2.0-2.4 m
    # above the 10 m datum; its top is the highest ground plus 6 m.
    assert column_top[1] == pytest.approx(2.4 + 6.0, abs=0.01)
    assert out.png.stat().st_size > 10_000


def test_builds_the_demo_site(tmp_path: Path) -> None:
    out = build_demo_scene(tmp_path)
    gltf = _gltf(out.glb)
    names = {n["name"] for n in gltf["nodes"]}
    assert {"Terrain", "AboveGround", "Parcel.0", "Parcel.3"} <= names
    low, high = _bounds(gltf, "Terrain")
    assert high[1] - low[1] < 10.0  # Reefton site: flat, ~2 m relief plus margin
    assert out.png.stat().st_size > 10_000


def test_parcel_edges_drape_over_the_ground_between_corners(tmp_path: Path) -> None:
    dem = np.full((40, 50), 10.0)
    dem[:, 19:22] = 12.0  # a 2 m ridge, 3 cells wide, running north-south at x = 19-22
    grid = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    ring = ((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0))
    scene = scene_input(grid, LocalFrame.centred_on(grid.bbox), [ring])

    gltf = _gltf(build_scene(scene, tmp_path).glb)

    _, top = _bounds(gltf, "Parcel.0")
    assert top[1] > 2.0  # crosses the ridge (2 m above the 10 m datum), not under it


def test_the_camera_looks_at_the_terrain_whatever_the_datum(tmp_path: Path) -> None:
    dem = np.full((40, 50), 190.0)
    grid = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    scene = scene_input(grid, LocalFrame.centred_on(grid.bbox), [], datum_m=0.0)

    gltf = _gltf(build_scene(scene, tmp_path).glb)

    camera = next(n for n in gltf["nodes"] if n["name"] == "Camera")
    assert camera["translation"][1] > 190.0  # glTF y is up


def test_a_one_cell_ridge_under_an_edge_is_not_skipped(tmp_path: Path) -> None:
    dem = np.full((40, 50), 10.0)
    dem[:, 21] = 12.0  # one cell wide: x 21-22, centre 21.5
    grid = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    ring = ((10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0), (10.0, 10.0))
    scene = scene_input(grid, LocalFrame.centred_on(grid.bbox), [ring])

    _, top = _bounds(_gltf(build_scene(scene, tmp_path).glb), "Parcel.0")

    assert top[1] > 2.0
