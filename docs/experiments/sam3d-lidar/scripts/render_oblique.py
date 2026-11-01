"""Blender: drape the aerial on the DSM, render a virtual oblique photo, and ray-cast its exact pointmap.

usage: blender -b --factory-startup --python-exit-code 1 -P render_oblique.py -- \
    SCENE_DIR AERIAL_PNG AZIMUTH_DEG PITCH_DEG DISTANCE_M [WIDTH HEIGHT LENS_MM]

AZIMUTH: compass bearing from the building to the camera (225 = camera to the south-west).
PITCH: camera's angle below horizontal.
Writes SCENE_DIR/oblique.png and SCENE_DIR/raycast.npz:
  world (H,W,3) hit points in the local frame (NaN where the ray misses),
  cam_cv (H,W,3) the same in OpenCV camera coords (x right, y down, z forward),
  K (3,3) pixel intrinsics, cam_to_world (4,4) in Blender's camera convention.
"""

import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1 :]
scene_dir, aerial_png = Path(argv[0]), Path(argv[1])
azimuth, pitch, distance = (float(v) for v in argv[2:5])
width, height, lens = (int(argv[5]), int(argv[6]), float(argv[7])) if len(argv) > 5 else (1024, 768, 35.0)
SENSOR_MM = 36.0

data = np.load(scene_dir / "scene.npz")
dsm, cell = data["dsm"], float(data["cell"])
west, south, east, north = data["bbox_local"]

# --- terrain mesh: one vertex per DSM cell centre, UVs onto the aerial's bbox
rows, cols = dsm.shape
xs = west + (np.arange(cols) + 0.5) * cell
ys = north - (np.arange(rows) + 0.5) * cell
gx, gy = np.meshgrid(xs, ys)
verts = np.stack([gx, gy, dsm], axis=-1).reshape(-1, 3)
idx = np.arange(rows * cols).reshape(rows, cols)
quads = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], axis=-1).reshape(-1, 4)
mesh = bpy.data.meshes.new("terrain")
mesh.vertices.add(len(verts))
mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
mesh.loops.add(quads.size)
mesh.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
mesh.polygons.add(len(quads))
mesh.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
mesh.polygons.foreach_set("loop_total", np.full(len(quads), 4, dtype=np.int32))
uv = np.stack([(verts[:, 0] - west) / (east - west), (verts[:, 1] - south) / (north - south)], axis=-1)
mesh.uv_layers.new(name="uv").data.foreach_set("uv", uv[quads.ravel()].astype(np.float32).ravel())
mesh.update()
mesh.validate()
terrain = bpy.data.objects.new("terrain", mesh)
scene = bpy.context.scene
for obj in list(scene.objects):
    bpy.data.objects.remove(obj)
scene.collection.objects.link(terrain)

# --- unlit material: the aerial already carries its own light
mat = bpy.data.materials.new("aerial")
mat.use_nodes = True
nodes, links = mat.node_tree.nodes, mat.node_tree.links
nodes.clear()
tex = nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(str(aerial_png))
tex.interpolation = "Linear"
emit = nodes.new("ShaderNodeEmission")
out = nodes.new("ShaderNodeOutputMaterial")
links.new(tex.outputs["Color"], emit.inputs["Color"])
links.new(emit.outputs["Emission"], out.inputs["Surface"])
mesh.materials.append(mat)

# --- camera looking at the outline's centroid, half way up the building
target_z = float(np.nanmedian(dsm[rows // 2 - 4 : rows // 2 + 4, cols // 2 - 4 : cols // 2 + 4])) - 1.5
target = Vector((0.0, 0.0, target_z))
az, pt = math.radians(azimuth), math.radians(pitch)
offset = Vector((math.sin(az) * math.cos(pt), math.cos(az) * math.cos(pt), math.sin(pt))) * distance
cam_data = bpy.data.cameras.new("cam")
cam_data.lens, cam_data.sensor_width, cam_data.sensor_fit = lens, SENSOR_MM, "HORIZONTAL"
cam = bpy.data.objects.new("cam", cam_data)
cam.location = target + offset
cam.rotation_euler = (-offset).to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(cam)
scene.camera = cam

world = bpy.data.worlds.new("sky")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.82, 0.9, 1.0)
scene.world = world
scene.render.engine = "CYCLES"
scene.cycles.samples = 32
scene.cycles.device = "CPU"
scene.view_settings.view_transform = "Standard"  # keep the photo's colours as they are
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = width, height, 100
scene.render.filepath = str(scene_dir / "oblique.png")
scene.render.image_settings.file_format = "PNG"
bpy.context.view_layer.update()
bpy.ops.render.render(write_still=True)

# --- exact pointmap: one ray per pixel centre, through the same pinhole
f_px = lens / SENSOR_MM * width
K = np.array([[f_px, 0, width / 2], [0, f_px, height / 2], [0, 0, 1.0]])
cam_to_world = np.array(cam.matrix_world)
depsgraph = bpy.context.evaluated_depsgraph_get()
bvh = BVHTree.FromObject(terrain, depsgraph)
origin = cam.matrix_world.translation.copy()
rot = cam.matrix_world.to_3x3()
world_pts = np.full((height, width, 3), np.nan)
for v in range(height):
    for u in range(width):
        # Blender camera: x right, y up, looking down -z
        d = rot @ Vector(((u + 0.5 - width / 2) / f_px, -(v + 0.5 - height / 2) / f_px, -1.0))
        hit, _, _, _ = bvh.ray_cast(origin, d.normalized())
        if hit is not None:
            world_pts[v, u] = hit
world_to_cam = np.linalg.inv(cam_to_world)
homog = np.concatenate([world_pts, np.ones((height, width, 1))], axis=-1)
cam_bl = (homog @ world_to_cam.T)[..., :3]
cam_cv = cam_bl * np.array([1.0, -1.0, -1.0])
np.savez(scene_dir / "raycast.npz", world=world_pts, cam_cv=cam_cv, K=K, cam_to_world=cam_to_world)
print(f"RAYCAST_OK hits {np.isfinite(world_pts[..., 0]).mean():.3f} cam {tuple(cam.location)}")
