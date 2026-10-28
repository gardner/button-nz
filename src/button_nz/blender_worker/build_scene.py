"""Build the site scene inside Blender, then export GLB and render a PNG.

Run by ``button_nz.blender_worker.run``:

    blender -b --factory-startup --python-exit-code 1 --python build_scene.py \\
        -- scene.json scene.glb scene.png

This file runs in Blender's own Python, so it imports only ``bpy`` and the
standard library. The scene JSON comes from ``scene_input``: a local metre
frame, x east, y north, z up, heights relative to ``frame.datum_m``.

Objects:
- ``Terrain``: one vertex per DEM cell centre, two triangles per cell.
- ``AboveGround``: a column per cell whose nDSM exceeds ``COLUMN_MIN_M``,
  marking measured above-ground evidence (structures or vegetation), not
  modelled buildings.
- ``Parcel.<n>``: each parcel boundary as a polyline just above the ground,
  sampled every half cell along each edge and placed on the interpolated
  surface, so it follows the terrain between corners on slopes too.
"""

import json
import math
import os
import sys
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_math as _terrain_math  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
terrain_math: Any = _terrain_math  # imported by path inside Blender

COLUMN_MIN_M = 2.0
BOUNDARY_LIFT_M = 0.15


def main(argv: list[str]) -> None:
    scene_path, glb_path, png_path = argv[argv.index("--") + 1 :]
    with open(scene_path, encoding="utf-8") as f:
        scene: dict[str, Any] = json.load(f)
    b.ops.wm.read_factory_settings(use_empty=True)
    terrain = scene["terrain"]
    _terrain(terrain)
    _columns(terrain, scene["ndsm"])
    for i, ring in enumerate(scene["parcels"]):
        _boundary(f"Parcel.{i}", ring, terrain)
    _camera_and_light(terrain)
    b.ops.export_scene.gltf(
        filepath=glb_path, export_format="GLB", export_apply=True, export_cameras=True
    )
    _render(png_path)


def _material(name: str, rgba: tuple[float, float, float, float]) -> Any:
    material = b.data.materials.new(name)
    material.diffuse_color = rgba
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = rgba
    return material


def _object(name: str, data: Any, material: Any) -> Any:
    obj = b.data.objects.new(name, data)
    data.materials.append(material)
    b.context.scene.collection.objects.link(obj)
    return obj


def _terrain(grid: dict[str, Any]) -> None:
    rows, cols, cell = grid["rows"], grid["cols"], grid["cell_m"]
    heights = grid["heights"]
    verts = [
        (grid["x0"] + c * cell, grid["y0"] - r * cell, heights[r * cols + c])
        for r in range(rows)
        for c in range(cols)
    ]
    faces = terrain_math.terrain_faces(rows, cols)  # the triangles height_at samples
    mesh = b.data.meshes.new("Terrain")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    _object("Terrain", mesh, _material("Ground", (0.32, 0.45, 0.22, 1.0)))


def _columns(terrain: dict[str, Any], ndsm: dict[str, Any]) -> None:
    cols, cell, half = ndsm["cols"], ndsm["cell_m"], ndsm["cell_m"] / 2
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for i, height in enumerate(ndsm["heights"]):
        if height <= COLUMN_MIN_M:
            continue
        r, c = divmod(i, cols)
        x, y = ndsm["x0"] + c * cell, ndsm["y0"] - r * cell
        z0 = terrain["heights"][i]
        n = len(verts)
        for z in (z0, z0 + height):
            verts += [(x - half, y - half, z), (x + half, y - half, z)]
            verts += [(x + half, y + half, z), (x - half, y + half, z)]
        faces += [(n, n + 3, n + 2, n + 1), (n + 4, n + 5, n + 6, n + 7)]
        faces += [(n + k, n + (k + 1) % 4, n + 4 + (k + 1) % 4, n + 4 + k) for k in range(4)]
    mesh = b.data.meshes.new("AboveGround")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    _object("AboveGround", mesh, _material("Evidence", (0.85, 0.45, 0.12, 1.0)))


def _boundary(name: str, ring: list[list[float]], terrain: dict[str, Any]) -> None:
    curve = b.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.08
    spline = curve.splines.new("POLY")
    # Every half cell, so no cell centre (a terrain vertex) is ever skipped.
    points: list[tuple[float, float]] = terrain_math.densify(ring, terrain["cell_m"] / 2)
    spline.points.add(len(points) - 1)
    for point, (x, y) in zip(spline.points, points, strict=True):
        point.co = (x, y, terrain_math.height_at(terrain, x, y) + BOUNDARY_LIFT_M, 1.0)
    _object(name, curve, _material("Boundary", (0.9, 0.1, 0.1, 1.0)))


def _camera_and_light(grid: dict[str, Any]) -> None:
    width = grid["cols"] * grid["cell_m"]
    depth = grid["rows"] * grid["cell_m"]
    centre = (grid["x0"] + width / 2, grid["y0"] - depth / 2)
    ground = (min(grid["heights"]) + max(grid["heights"])) / 2  # whatever the datum
    distance = max(width, depth) * 1.1
    camera = b.data.objects.new("Camera", b.data.cameras.new("Camera"))
    camera.location = (centre[0], centre[1] - distance, ground + distance * 0.9)
    camera.rotation_euler = (math.radians(48), 0.0, 0.0)
    b.context.scene.collection.objects.link(camera)
    b.context.scene.camera = camera
    sun = b.data.objects.new("Sun", b.data.lights.new("Sun", type="SUN"))
    sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(30))
    sun.data.energy = 3.0
    b.context.scene.collection.objects.link(sun)


def _render(png_path: str) -> None:
    scene = b.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.render.resolution_x, scene.render.resolution_y = 1280, 960
    scene.render.filepath = png_path
    _use_gpu(scene)
    b.ops.render.render(write_still=True)


def _use_gpu(scene: Any) -> None:
    """Render on the GPU. No usable GPU is an error, not a slow CPU render."""
    prefs = b.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for device in prefs.devices:
                device.use = device.type == backend
            scene.cycles.device = "GPU"
            return
    raise RuntimeError("no GPU available to Cycles")


if __name__ == "__main__":
    main(sys.argv)
