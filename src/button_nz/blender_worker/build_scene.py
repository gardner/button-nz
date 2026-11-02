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
- ``Parcel.<n>``: each parcel boundary as a polyline a constant height above
  the rendered ground, with a point wherever it crosses a mesh triangle edge.
"""

import json
import math
import os
import sys
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]
import mathutils as _mathutils  # pyright: ignore[reportMissingImports]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_math as _terrain_math  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
mathutils: Any = _mathutils
terrain_math: Any = _terrain_math  # imported by path inside Blender

COLUMN_MIN_M = 2.0
BOUNDARY_LIFT_M = 0.15
SKY_STRENGTH = 0.25  # the sky's light beside the Sun lamp's
HAZE = (0.3, 0.5, 0.9, 1.0)  # behind the site, as the camera sees it


def main(argv: list[str]) -> None:
    scene_path, glb_path, png_path = argv[argv.index("--") + 1 :]
    build(load(scene_path))
    export(glb_path, png_path)


def load(scene_path: str) -> dict[str, Any]:
    with open(scene_path, encoding="utf-8") as f:
        scene: dict[str, Any] = json.load(f)
    return scene


def build(scene: dict[str, Any]) -> None:
    """Build the site in an empty Blender scene: terrain, evidence, parcels, camera."""
    b.ops.wm.read_factory_settings(use_empty=True)
    terrain = scene["terrain"]
    _terrain(terrain)
    _columns(terrain, scene["ndsm"])
    for i, ring in enumerate(scene["parcels"]):
        _boundary(f"Parcel.{i}", ring, terrain)
    _camera_and_light(terrain)


def export(glb_path: str, png_path: str) -> None:
    """Export the scene as GLB (with its camera) and render it on the GPU."""
    b.ops.export_scene.gltf(
        filepath=glb_path, export_format="GLB", export_apply=True, export_cameras=True
    )
    _render(png_path)


def material(name: str, rgba: tuple[float, float, float, float]) -> Any:
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
    _object("Terrain", mesh, material("Ground", (0.32, 0.45, 0.22, 1.0)))


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
    _object("AboveGround", mesh, material("Evidence", (0.85, 0.45, 0.12, 1.0)))


def _boundary(name: str, ring: list[list[float]], terrain: dict[str, Any]) -> None:
    curve = b.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.08
    spline = curve.splines.new("POLY")
    # A point at every crossing of a mesh triangle edge, so each straight
    # segment lies on one flat triangle and stays exactly BOUNDARY_LIFT_M up.
    points: list[tuple[float, float]] = terrain_math.mesh_crossings(ring, terrain)
    spline.points.add(len(points) - 1)
    for point, (x, y) in zip(spline.points, points, strict=True):
        point.co = (x, y, terrain_math.height_at(terrain, x, y) + BOUNDARY_LIFT_M, 1.0)
    _object(name, curve, material("Boundary", (0.9, 0.1, 0.1, 1.0)))


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
    turn = mathutils.Euler((math.radians(40), math.radians(15), math.radians(30)))
    sun.rotation_euler = turn
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.95, 0.88)  # mid-morning: a little warm
    sun.data.angle = math.radians(0.53)  # the sun's own width: soft-edged shadows
    b.context.scene.collection.objects.link(sun)
    _sky(turn.to_matrix() @ mathutils.Vector((0.0, 0.0, 1.0)))


def _sky(towards_sun: Any) -> None:
    """A clear daylight sky lights the site, its sun where the Sun lamp shines
    from (the lamp draws the sun's light and shadows, so the sky draws no sun
    disc). The camera, looking down, would see the sky below the horizon, so
    behind the site it sees a hazy blue instead."""
    world = b.data.worlds.new("Sky")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.asin(towards_sun.z)
    sky.sun_rotation = math.atan2(towards_sun.x, towards_sun.y)
    lit = nodes["Background"]
    lit.inputs["Strength"].default_value = SKY_STRENGTH
    links.new(sky.outputs["Color"], lit.inputs["Color"])
    seen = nodes.new("ShaderNodeBackground")
    seen.inputs["Color"].default_value = HAZE
    mix = nodes.new("ShaderNodeMixShader")
    links.new(nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], mix.inputs["Fac"])
    links.new(lit.outputs["Background"], mix.inputs[1])
    links.new(seen.outputs["Background"], mix.inputs[2])
    links.new(mix.outputs["Shader"], nodes["World Output"].inputs["Surface"])
    b.context.scene.world = world


def _render(png_path: str) -> None:
    scene = b.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.view_settings.look = "AgX - Medium High Contrast"  # daylight, not haze
    scene.render.resolution_x, scene.render.resolution_y = 1280, 960
    scene.render.filepath = png_path
    use_gpu(scene)
    b.ops.render.render(write_still=True)


def render_silhouette(png_path: str, name: str) -> None:
    """Render, from the same camera at the same size, white where the object
    ``name`` is visible and black elsewhere. Every other object stays where it
    is, in black, so a tree in front of the house hides that part of it. One
    Cycles sample of unlit emission per pixel, through a box filter narrower
    than the pixel, gives exactly two values. (Workbench needs OpenGL, which
    the sandbox doesn't have.)"""
    scene = b.context.scene
    white, black = _emission("Silhouette", 1.0), _emission("Background", 0.0)
    for obj in scene.objects:
        if obj.data is not None and hasattr(obj.data, "materials"):
            obj.data.materials.clear()
            obj.data.materials.append(white if obj.name == name else black)
    scene.world = b.data.worlds.new("Silhouette")
    scene.world.use_nodes = True  # a new world's background is grey, not black
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    scene.cycles.samples, scene.cycles.use_adaptive_sampling = 1, False
    scene.cycles.use_denoising, scene.cycles.max_bounces = False, 0
    scene.cycles.pixel_filter_type, scene.cycles.filter_width = "BOX", 0.01
    scene.render.film_transparent, scene.render.dither_intensity = False, 0.0
    scene.view_settings.view_transform, scene.view_settings.look = "Standard", "None"
    scene.view_settings.exposure, scene.view_settings.gamma = 0.0, 1.0
    scene.render.image_settings.color_mode = "BW"
    scene.render.filepath = png_path
    b.ops.render.render(write_still=True)


def render_outline(png_path: str, name: str) -> None:
    """``render_silhouette`` with every other object hidden: the whole of
    ``name`` from the camera, nothing in front of it."""
    for obj in b.context.scene.objects:
        obj.hide_render = obj.name != name
    render_silhouette(png_path, name)


def _emission(name: str, value: float) -> Any:
    """An unlit material of grey ``value``: the same in the render, whatever the light."""
    material = b.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (value, value, value, 1.0)
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def use_gpu(scene: Any) -> None:
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
