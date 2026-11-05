"""The design loop end to end, a spec through real sandboxed Blender and the
real evaluator; and the trusted passes with scripts of every kind. Run with
`pytest -m blender`."""

import json
import re
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.agent.conversation import Turn
from button_nz.agent.loop import DesignSite, design
from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.blender_worker.run import run_design
from button_nz.blender_worker.scene_input import DwellingFinishes, scene_input, with_finishes
from button_nz.evaluation import Report, SiteContext, Status, evaluate
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender

# A 6 m x 5 m, 3.6 m tall dwelling whose floor sits 0.3 m above the ground: a
# script, as the trusted passes see any script, built by the spec builder or not.
DWELLING = """
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, 0.0, 0.3 + 1.8))
dwelling = bpy.context.active_object
dwelling.name = "Dwelling"
dwelling.scale = (6.0, 5.0, 3.6)
dwelling["floor_area_m2"] = 26.0
dwelling["storeys"] = 1
"""
MOVED = DWELLING.format(x=0.0)
PLACED = re.compile(r"  - 1: .*?floor underside at z (-?[0-9.]+) to")


class SpecModel:
    """Proposes a gable on placement 1, its floor at the lowest level offered;
    then, told a check failed, the same with a flat roof."""

    def __init__(self) -> None:
        self.feedback: list[str] = []

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        found = PLACED.search(conversation[0].text)
        assert found is not None
        roof = {"form": "gable", "pitch_deg": 15}
        if conversation[-1].role == "feedback":
            self.feedback.append(conversation[-1].text)
            roof = {"form": "flat", "pitch_deg": 0}
        spec = {"placement": 1, "floor_z_m": float(found[1]), "roof": roof, "eaves_m": 0.6}
        return json.dumps(spec)


def flat_site() -> DesignSite:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)
    return DesignSite(
        scene_input(grid, frame, [parcel]), frame, SiteContext(parcels=(parcel,), terrain=grid)
    )


def test_a_spec_is_built_measured_and_accepted(tmp_path: Path) -> None:
    result = design("A 60 m² home.", flat_site(), SpecModel(), tmp_path)

    assert result.accepted is result.attempts[0]
    report = result.attempts[0].report
    assert report is not None
    statuses = {c.name: c.status for c in report.checks}
    assert statuses["title_boundary_setback"] is Status.PASS
    assert statuses["floor_level"] is statuses["height"] is Status.PASS
    assert (tmp_path / "attempt-1" / "design.glb").is_file()
    trace = json.loads((tmp_path / "attempt-1" / "attempt.json").read_text(encoding="utf-8"))
    assert json.loads(trace["spec"])["roof"]["form"] == "gable"
    summary = json.loads((tmp_path / "design.json").read_text(encoding="utf-8"))
    assert summary["accepted_attempt"] == 1


def test_the_demo_site_runs_through_the_loop(tmp_path: Path) -> None:
    """The real site (from LINZ's S3) with the scripted model: the wiring the
    Muse demo uses, minus the API key."""
    from button_nz.agent.demo import run

    result = run(tmp_path, "A small studio.", SpecModel())
    assert result.attempts[0].report is not None
    by_name = {c.name: c for c in result.attempts[0].report.checks}
    assert 189.0 < by_name["floor_level"].measured["lowest_ground_m"] < 191.5


def run_script(script: str, out_dir: Path, finishes: DwellingFinishes | None = None) -> Report:
    """``script`` through the trusted passes on the flat site, measured and checked."""
    site = flat_site()
    scene = site.scene if finishes is None else with_finishes(site.scene, finishes)
    outputs = run_design(scene, script, out_dir)
    datum = float(site.scene["frame"]["datum_m"])
    proposal = to_proposal(parse_measurements(outputs.measurements), site.frame, datum)
    return evaluate(proposal, site.context)


def test_the_render_finishes_the_roof_and_walls_as_the_host_says(tmp_path: Path) -> None:
    finishes: DwellingFinishes = {
        "walls": {"rgba": [0.9, 0.1, 0.1, 1.0], "texture": "white_planks_clean"},
        "roof": {"rgba": [0.1, 0.1, 0.9, 1.0], "texture": "corrugated_iron"},
    }

    report = run_script(MOVED, tmp_path / "attempt-1", finishes)

    assert report.status is not Status.FAIL
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


# A mirrored dwelling: every triangle wound the other way.
MIRRORED = MOVED.replace("(6.0, 5.0, 3.6)", "(6.0, 5.0, -3.6)")


def test_the_roof_is_the_roof_whichever_way_its_triangles_wind(tmp_path: Path) -> None:
    report = run_script(MIRRORED, tmp_path / "attempt-1")

    assert report.status is not Status.FAIL
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


def test_a_deck_is_not_roof(tmp_path: Path) -> None:
    run_design(flat_site().scene, WITH_DECK, tmp_path / "attempt-1")  # rendered, not checked

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


# Leaves a Dwelling mesh with no faces.
EMPTY = """
dwelling = bpy.data.objects.new("Dwelling", bpy.data.meshes.new("Dwelling"))
bpy.context.collection.objects.link(dwelling)
"""


def test_an_empty_dwelling_is_feedback_not_a_crash(tmp_path: Path) -> None:
    with pytest.raises(DesignError, match="Dwelling"):
        run_script(EMPTY, tmp_path / "attempt-1")
