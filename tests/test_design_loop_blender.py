"""The design loop end to end: real sandboxed Blender, real evaluator, and a
scripted model that revises after a failed check. Run with `pytest -m blender`."""

import json
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.agent.conversation import Turn
from button_nz.agent.loop import DesignSite, design
from button_nz.blender_worker.scene_input import DwellingFinishes, scene_input
from button_nz.evaluation import SiteContext, Status
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender

# A 6 m x 5 m, 3.6 m tall dwelling whose floor sits 0.3 m above the ground.
DWELLING = """
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, 0.0, 0.3 + 1.8))
dwelling = bpy.context.active_object
dwelling.name = "Dwelling"
dwelling.scale = (6.0, 5.0, 3.6)
dwelling["floor_area_m2"] = 26.0
dwelling["storeys"] = 1
"""
TOO_CLOSE = DWELLING.format(x=-16.5)  # west wall 0.5 m from the title boundary
MOVED = DWELLING.format(x=0.0)


class RevisingModel:
    """Places the dwelling too close, then moves it once told the setback failed."""

    def __init__(self) -> None:
        self.feedback: list[str] = []

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        if conversation[-1].role != "feedback":
            return TOO_CLOSE
        self.feedback.append(conversation[-1].text)
        return MOVED if "title_boundary_setback: fail" in conversation[-1].text else TOO_CLOSE


def test_a_failed_placement_is_revised_and_accepted(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)  # local x -20..20, y -10..10
    site = DesignSite(
        scene_input(grid, frame, [parcel]),
        frame,
        SiteContext(parcels=(parcel,), terrain=grid),
    )
    model = RevisingModel()

    result = design("A 26 m² studio.", site, model, tmp_path)

    first, second = result.attempts
    assert first.report is not None and first.report.status is Status.FAIL
    setback = next(c for c in first.report.checks if c.name == "title_boundary_setback")
    assert setback.measured["distance_m"] == pytest.approx(0.5, abs=1e-6)
    assert "0.50 m from the title boundary" in model.feedback[0]
    assert result.accepted is second
    assert second.report is not None
    statuses = {c.name: c.status for c in second.report.checks}
    assert statuses["title_boundary_setback"] is Status.PASS
    assert statuses["floor_level"] is Status.PASS  # floor 0.3 m above flat ground
    assert (tmp_path / "attempt-2" / "design.glb").is_file()
    summary = json.loads((tmp_path / "design.json").read_text(encoding="utf-8"))
    assert summary["accepted_attempt"] == 2


def test_the_demo_site_runs_through_the_loop(tmp_path: Path) -> None:
    """The real site (from LINZ's S3) with the scripted model: the wiring the
    Muse demo uses, minus the API key."""
    from button_nz.agent.demo import run

    result = run(tmp_path, "A small studio.", RevisingModel())
    assert result.attempts[0].report is not None
    by_name = {c.name: c for c in result.attempts[0].report.checks}
    assert 189.0 < by_name["floor_level"].measured["lowest_ground_m"] < 191.5


class PlacingModel:
    """Places the dwelling well inside the title, once."""

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        return MOVED


def test_the_render_finishes_the_roof_and_walls_as_the_host_says(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)
    site = DesignSite(
        scene_input(grid, frame, [parcel]), frame, SiteContext(parcels=(parcel,), terrain=grid)
    )
    finishes: DwellingFinishes = {
        "walls": {"rgba": [0.9, 0.1, 0.1, 1.0], "texture": "white_planks_clean"},
        "roof": {"rgba": [0.1, 0.1, 0.9, 1.0], "texture": "corrugated_iron"},
    }

    result = design("A studio.", site, PlacingModel(), tmp_path, finishes=finishes)

    assert result.accepted is not None
    glb = tmp_path / "attempt-1" / "design.glb"
    assert glb.stat().st_size < 10_000_000
    gltf = glb_json(glb)
    node = next(n for n in gltf["nodes"] if n["name"] == "Dwelling")
    primitives = gltf["meshes"][node["mesh"]]["primitives"]
    assert all("TEXCOORD_0" in p["attributes"] for p in primitives)
    materials = {
        gltf["materials"][p["material"]]["name"]: gltf["materials"][p["material"]]
        for p in primitives
    }
    for name, part, tile_m in (("Dwelling walls", "walls", 3.8), ("Dwelling roof", "roof", 1.12)):
        pbr = materials[name]["pbrMetallicRoughness"]
        assert pbr["baseColorFactor"] == pytest.approx(finishes[part]["rgba"], abs=1e-3)
        colour = pbr["baseColorTexture"]
        image = gltf["images"][gltf["textures"][colour["index"]]["source"]]
        assert finishes[part]["texture"] in image["name"]
        assert "normalTexture" in materials[name]
        transform = colour["extensions"]["KHR_texture_transform"]
        assert [abs(s) for s in transform["scale"]] == pytest.approx([1 / tile_m] * 2, rel=1e-3)
        assert transform.get("rotation", 0.0) == pytest.approx(0.0)  # turned in the UVs
    walls = next(
        p for p in primitives if materials["Dwelling walls"] is gltf["materials"][p["material"]]
    )
    corners = glb_values(glb, gltf, walls["indices"]).reshape(-1, 3)
    position = glb_values(glb, gltf, walls["attributes"]["POSITION"])  # glTF: y is up
    uv = glb_values(glb, gltf, walls["attributes"]["TEXCOORD_0"])
    upright = [t for t in corners if np.ptp(position[t][:, 1]) > 1.0]  # the walls, not floor
    on_walls = uv[np.unique(np.concatenate(upright))]
    across, along = on_walls.max(axis=0) - on_walls.min(axis=0)
    assert across == pytest.approx(3.6, abs=0.01)  # weatherboards: u runs up the wall,
    assert along > 5.0  # and v along it, so the boards and their relief run level


class MirroringModel:
    """Places a mirrored dwelling: every triangle wound the other way."""

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        return MOVED.replace("(6.0, 5.0, 3.6)", "(6.0, 5.0, -3.6)")


def test_the_roof_is_the_roof_whichever_way_its_triangles_wind(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)
    site = DesignSite(
        scene_input(grid, frame, [parcel]), frame, SiteContext(parcels=(parcel,), terrain=grid)
    )

    result = design("A studio.", site, MirroringModel(), tmp_path)

    assert result.accepted is not None
    gltf = glb_json(tmp_path / "attempt-1" / "design.glb")
    node = next(n for n in gltf["nodes"] if n["name"] == "Dwelling")
    top = {
        gltf["materials"][p["material"]]["name"]: gltf["accessors"][p["attributes"]["POSITION"]][
            "max"
        ][1]
        for p in gltf["meshes"][node["mesh"]]["primitives"]
    }
    assert top["Dwelling roof"] == pytest.approx(top["Dwelling walls"])  # the top face is roof


# The dwelling above with a 0.2 m deck slab along its south side, in one mesh.
WITH_DECK = (
    MOVED
    + """
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.0, -3.5, 0.2))
deck = bpy.context.active_object
deck.scale = (6.0, 2.0, 0.2)
bpy.ops.object.select_all(action="DESELECT")
deck.select_set(True)
dwelling.select_set(True)
bpy.context.view_layer.objects.active = dwelling
bpy.ops.object.join()
"""
)


class DeckModel:
    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        return WITH_DECK


def test_a_deck_is_not_roof(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)
    site = DesignSite(
        scene_input(grid, frame, [parcel]), frame, SiteContext(parcels=(parcel,), terrain=grid)
    )

    design("A studio with a deck.", site, DeckModel(), tmp_path, max_attempts=1)

    gltf = glb_json(tmp_path / "attempt-1" / "design.glb")
    node = next(n for n in gltf["nodes"] if n["name"] == "Dwelling")
    lowest = {
        gltf["materials"][p["material"]]["name"]: gltf["accessors"][p["attributes"]["POSITION"]][
            "min"
        ][1]
        for p in gltf["meshes"][node["mesh"]]["primitives"]
    }
    assert lowest["Dwelling roof"] == pytest.approx(3.9)  # only the top: not the deck or floor


def glb_json(glb: Path) -> dict[str, Any]:
    """The JSON chunk of a GLB file."""
    data = glb.read_bytes()
    (chunk_length,) = struct.unpack_from("<I", data, 12)
    found: dict[str, Any] = json.loads(data[20 : 20 + chunk_length])
    return found


COMPONENTS = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}


def glb_values(glb: Path, gltf: dict[str, Any], accessor: int) -> NDArray[Any]:
    """An accessor's values (indices, positions, UVs), one row each, from the
    GLB's binary chunk; assumes tightly packed views, as Blender writes them."""
    data = glb.read_bytes()
    (json_length,) = struct.unpack_from("<I", data, 12)
    binary = 20 + json_length + 8  # past the JSON chunk and the BIN chunk's header
    found = gltf["accessors"][accessor]
    view = gltf["bufferViews"][found["bufferView"]]
    start = binary + view.get("byteOffset", 0) + found.get("byteOffset", 0)
    width = WIDTHS[found["type"]]
    values = np.frombuffer(data, COMPONENTS[found["componentType"]], found["count"] * width, start)
    return values.reshape(-1, width) if width > 1 else values


class EmptyModel:
    """Leaves a Dwelling mesh with no faces."""

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        return """
dwelling = bpy.data.objects.new("Dwelling", bpy.data.meshes.new("Dwelling"))
bpy.context.collection.objects.link(dwelling)
"""


def test_an_empty_dwelling_is_feedback_not_a_crash(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)
    site = DesignSite(
        scene_input(grid, frame, [parcel]), frame, SiteContext(parcels=(parcel,), terrain=grid)
    )

    result = design("A studio.", site, EmptyModel(), tmp_path, max_attempts=1)

    assert result.accepted is None
    assert "Dwelling" in result.attempts[0].feedback
