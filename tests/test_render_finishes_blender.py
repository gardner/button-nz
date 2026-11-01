"""The trusted render's finishes can't be swapped by the model's script. Real
sandboxed Blender; run with `pytest -m blender`."""

import io
import os
import struct
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from button_nz import blender_worker
from button_nz.agent.conversation import Turn
from button_nz.agent.loop import DesignSite, design
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid
from test_design_loop_blender import MOVED, glb_json

pytestmark = pytest.mark.blender

WEATHERBOARD = Path(blender_worker.__file__).with_name("textures") / "white_planks_clean_detail.jpg"

# The model packs its own red image, on a material of its Dwelling, under a
# path that resolves to the committed texture from where the host keeps its
# saved file, hoping the trusted pass picks it up as the texture.
SWAPPING = """
fake = bpy.data.images.new("fake", 8, 8)
fake.pixels = [1.0, 0.0, 0.0, 1.0] * 64
fake.pack()
fake.filepath_raw = {path!r}
bpy.app.handlers.save_pre.append(lambda *_: setattr(fake, "filepath_raw", {path!r}))
material = bpy.data.materials.new("Fake")
material.use_nodes = True
material.node_tree.nodes.new("ShaderNodeTexImage").image = fake
dwelling.data.materials.append(material)
"""


class SwappingModel:
    def __init__(self, saved: Path) -> None:
        self.path = "//" + os.path.relpath(WEATHERBOARD, saved)

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str:
        return MOVED + SWAPPING.format(path=self.path)


def test_the_models_image_at_a_textures_path_is_not_the_texture(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)
    site = DesignSite(
        scene_input(grid, frame, [parcel]), frame, SiteContext(parcels=(parcel,), terrain=grid)
    )

    design(
        "A studio.",
        site,
        SwappingModel(tmp_path / "attempt-1" / "script"),
        tmp_path,
        max_attempts=1,
    )

    glb = tmp_path / "attempt-1" / "design.glb"
    gltf = glb_json(glb)
    walls = next(m for m in gltf["materials"] if m["name"] == "Dwelling walls")
    texture = gltf["textures"][walls["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
    with Image.open(io.BytesIO(glb_image(glb, gltf, texture["source"]))) as image:
        assert image.size == (1024, 1024)  # the committed map, not the model's 8 px
        red, green, _ = np.asarray(image.convert("RGB"), dtype=float).mean(axis=(0, 1))
    assert red == pytest.approx(green, abs=5)  # greyscale detail, not red


def glb_image(glb: Path, gltf: dict[str, Any], index: int) -> bytes:
    """An embedded image's bytes, from the GLB's binary chunk."""
    data = glb.read_bytes()
    (json_length,) = struct.unpack_from("<I", data, 12)
    binary = 20 + json_length + 8
    view = gltf["bufferViews"][gltf["images"][index]["bufferView"]]
    start = binary + view.get("byteOffset", 0)
    return data[start : start + view["byteLength"]]
