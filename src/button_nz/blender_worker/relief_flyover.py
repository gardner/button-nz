"""Render the relief fly-over inside Blender: the aerial draped on the DSM.

Run by ``button_nz.relief.flyover``:

    blender -b --factory-startup --python-exit-code 1 --python relief_flyover.py \\
        -- flyover.json

This file runs in Blender's own Python, so it imports only ``bpy``, numpy
(which Blender bundles), the standard library and ``build_scene`` beside it.
``flyover.json`` names the DSM (``surface``, heights above the site's datum
in a local frame, x east, y north, row 0 the north edge), the aerial PNG over
the same ``bbox``, and the camera's ``poses``; one PNG is written per pose.

The terrain has one vertex per DSM cell centre and is unlit: its colour is
the photo's, which already carries the day's light. Its brightness is the
face's upward normal mapped from ``wall_shade`` (a wall) to 1 (flat ground),
so walls read as walls, as in the parallax tier.
"""

import json
import os
import sys
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]
import numpy as _numpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scene as _build_scene  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
np: Any = _numpy  # Blender's own numpy, which may not be the project's version
build_scene: Any = _build_scene  # imported by path inside Blender


def main(argv: list[str]) -> None:
    with open(argv[argv.index("--") + 1], encoding="utf-8") as f:
        spec = json.load(f)
    scene = b.context.scene
    for obj in list(scene.objects):
        b.data.objects.remove(obj)
    terrain = _terrain(np.load(spec["surface"]), spec["cell_m"], spec["bbox"])
    terrain.data.materials.append(_photo(spec["aerial"], spec["wall_shade"]))
    scene.collection.objects.link(terrain)
    camera = _camera(spec)
    scene.collection.objects.link(camera)
    scene.camera = camera
    _settings(scene, spec)
    for index, pose in enumerate(spec["poses"]):
        camera.location, camera.rotation_euler = pose["location"], pose["rotation"]
        scene.render.filepath = os.path.join(spec["frames_dir"], f"frame_{index:04d}.png")
        b.ops.render.render(write_still=True)


def _terrain(surface: Any, cell: float, bbox: list[float]) -> Any:
    west, south, east, north = bbox
    rows, cols = surface.shape
    xs = west + (np.arange(cols) + 0.5) * cell
    ys = north - (np.arange(rows) + 0.5) * cell
    gx, gy = np.meshgrid(xs, ys)
    verts = np.stack([gx, gy, surface], axis=-1).reshape(-1, 3)
    index = np.arange(rows * cols).reshape(rows, cols)
    quads = np.stack(
        [index[:-1, :-1], index[1:, :-1], index[1:, 1:], index[:-1, 1:]], axis=-1
    ).reshape(-1, 4)
    mesh = b.data.meshes.new("Relief")
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(quads.size)
    mesh.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
    mesh.polygons.add(len(quads))
    mesh.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
    mesh.polygons.foreach_set("loop_total", np.full(len(quads), 4, dtype=np.int32))
    uv = np.stack(
        [(verts[:, 0] - west) / (east - west), (verts[:, 1] - south) / (north - south)], 1
    )
    mesh.uv_layers.new(name="UVMap").data.foreach_set(
        "uv", uv[quads.ravel()].astype(np.float32).ravel()
    )
    mesh.update()
    mesh.validate()
    return b.data.objects.new("Relief", mesh)


def _photo(aerial: str, wall_shade: float) -> Any:
    material = b.data.materials.new("Aerial")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = b.data.images.load(aerial)
    texture.interpolation, texture.extension = "Linear", "EXTEND"
    upward = nodes.new("ShaderNodeSeparateXYZ")
    links.new(nodes.new("ShaderNodeNewGeometry").outputs["Normal"], upward.inputs["Vector"])
    shade = nodes.new("ShaderNodeMapRange")
    shade.inputs["To Min"].default_value = wall_shade
    links.new(upward.outputs["Z"], shade.inputs["Value"])
    emission = nodes.new("ShaderNodeEmission")
    links.new(texture.outputs["Color"], emission.inputs["Color"])
    links.new(shade.outputs["Result"], emission.inputs["Strength"])
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _camera(spec: dict[str, Any]) -> Any:
    data = b.data.cameras.new("Camera")
    data.lens, data.sensor_width, data.sensor_fit = spec["lens_mm"], spec["sensor_mm"], "HORIZONTAL"
    data.clip_start, data.clip_end = 0.1, spec["clip_end_m"]
    return b.data.objects.new("Camera", data)


def _settings(scene: Any, spec: dict[str, Any]) -> None:
    world = b.data.worlds.new("Sky")
    world.use_nodes = True
    sky = [_linear(channel / 255) for channel in spec["background"]]
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*sky, 1.0)
    scene.world = world
    scene.render.engine = "CYCLES"
    build_scene.use_gpu(scene)
    scene.cycles.samples, scene.cycles.use_denoising = spec["samples"], False
    scene.cycles.max_bounces = 0  # unlit: nothing to bounce
    scene.render.use_persistent_data = True  # only the camera moves between frames
    scene.view_settings.view_transform, scene.view_settings.look = "Standard", "None"
    scene.render.resolution_x, scene.render.resolution_y = spec["width"], spec["height"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"


def _linear(srgb: float) -> float:
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


if __name__ == "__main__":
    main(sys.argv)
