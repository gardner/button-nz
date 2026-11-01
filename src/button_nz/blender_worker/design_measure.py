"""Pass 2 of a design run: trusted measurement. Run sandboxed (it reads the
model's file) by ``button_nz.blender_worker.run.run_design``:

    blender -b --factory-startup --python-exit-code 1 --python design_measure.py \\
        -- scene.json design.blend OUT_DIR

No model code runs here. The site is rebuilt from ``scene.json``, so any change
the script made to it is discarded, and the GPU is chosen before anything of
the model's is touched: no GPU is Blender's failure, not the model's. Then the
model's objects are loaded from ``design.blend``. The contract: one mesh named
``Dwelling`` in the local frame, with its own transform (no parent, constraints
or drivers), optionally carrying ``floor_area_m2`` and ``storeys``; no other
geometry, since only the Dwelling is measured. Other objects (lights, cameras)
are dropped. The Dwelling alone is added to the site, measured with its
evaluated transform, exported and rendered, so what is checked is what is shown.

Writes ``OUT_DIR/measurements.json``, then ``design.glb``, ``design.png`` and
``dwelling-mask.png``: the baked Dwelling's silhouette from the render camera,
with the site in front of it hiding what it hides.
A broken contract is recorded in the measurements for the model to fix.
"""

import math
import os
import sys
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scene as _build_scene  # noqa: E402  # pyright: ignore[reportMissingImports]
import design_io as _design_io  # noqa: E402  # pyright: ignore[reportMissingImports]
import finishes as _finishes  # noqa: E402  # pyright: ignore[reportMissingImports]
import surface_math as _surface_math  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
build_scene: Any = _build_scene
design_io: Any = _design_io
finishes: Any = _finishes
surface_math: Any = _surface_math
MAX_TRIANGLES = 200_000
NOT_FINITE = "Some of the Dwelling's vertices aren't finite numbers (NaN or inf)."
# The Dwelling is rendered opaque in the host's finishes (the scene's
# ``dwelling_finishes``), whatever material the script gave: level faces in its
# upper half (roof planes, soffits) take the roof's, the rest (walls, floor,
# decks) the walls'. These are for a scene written before the host set them
# (button_nz.blender_worker.scene_input.DEFAULT_FINISHES).
DEFAULT_FINISHES = {
    "walls": {"rgba": [0.8, 0.75, 0.65, 1.0], "texture": "white_planks_clean"},
    "roof": {"rgba": [0.06, 0.07, 0.08, 1.0], "texture": "corrugated_iron"},
}
ROOF_NORMAL_Z = 0.5  # a face this near level, in the upper half, is roof (either winding)
UNREADABLE = "Your saved design couldn't be read ({reason}). Don't write to the results channel."
TOO_DETAILED = (
    "The Dwelling has {n} triangles, more than 200,000. Model the building's envelope, "
    "not its fine detail."
)


def main(argv: list[str]) -> None:
    scene_path, blend_path, out_dir = argv[argv.index("--") + 1 :]
    scene: dict[str, Any] = build_scene.load(scene_path)
    build_scene.build(scene)
    build_scene.use_gpu(b.context.scene)
    path = os.path.join(out_dir, "measurements.json")
    design_io.write_json(path, {"error": design_io.DID_NOT_FINISH})
    try:
        objects = _load(blend_path, design_io.site_names(scene))
    except (OSError, RuntimeError) as error:  # only the model's script could have spoilt it
        design_io.write_json(path, {"error": UNREADABLE.format(reason=error)})
        return
    error = _broken_contract(objects)
    if error is not None:
        design_io.write_json(path, {"error": error})
        return
    dwelling = objects["Dwelling"]
    b.context.scene.collection.objects.link(dwelling)
    _evaluate_as_rendered(dwelling)
    measurements: dict[str, Any] = {"error": None} | _measure(dwelling)
    if measurements["error"] is not None:  # e.g. too detailed: don't render it either
        design_io.write_json(path, measurements)
        return
    look: dict[str, Any] = scene.get("dwelling_finishes") or DEFAULT_FINISHES
    _bake(dwelling, measurements["triangles"], look)  # exactly what was measured
    design_io.write_json(path, measurements | {"error": design_io.DID_NOT_FINISH})
    build_scene.export(os.path.join(out_dir, "design.glb"), os.path.join(out_dir, "design.png"))
    design_io.write_json(path, measurements)  # the design is done: the silhouette is extra
    try:  # only the AI visual needs it, and its absence is recorded there
        build_scene.render_silhouette(os.path.join(out_dir, "dwelling-mask.png"), "Dwelling")
    except Exception as error:  # noqa: BLE001 - nothing about the design depends on it
        print(f"no silhouette: {error}", file=sys.stderr)


def _evaluate_as_rendered(dwelling: Any) -> None:
    """Make the Dwelling's modifiers evaluate as they render (the measuring
    depsgraph uses viewport settings)."""
    dwelling.hide_viewport = False
    for modifier in dwelling.modifiers:
        modifier.show_viewport = modifier.show_render
        if hasattr(modifier, "render_levels"):  # subdivision and multires
            modifier.levels = modifier.render_levels


def _load(blend_path: str, site: set[str]) -> dict[str, Any]:
    """The model's objects from its saved file, by name, linked to no scene yet."""
    with b.data.libraries.load(blend_path, link=False) as (source, target):
        target.objects = [name for name in source.objects if name not in site]
    return {obj.name: obj for obj in target.objects if obj is not None}


def _broken_contract(objects: dict[str, Any]) -> str | None:
    dwelling = objects.get("Dwelling")
    if dwelling is None or dwelling.type != "MESH":
        return (
            "Your script left no mesh object named Dwelling in the scene. Create it and "
            "link it: bpy.context.collection.objects.link(obj)."
        )
    if any(_asks_is_viewport(m.node_group) for m in dwelling.modifiers if m.type == "NODES"):
        return (
            "The Dwelling's Geometry Nodes use Is Viewport, so what is measured could "
            "differ from what renders. Build the geometry without it."
        )
    if dwelling.parent is not None or dwelling.constraints or dwelling.animation_data:
        return (
            "Give the Dwelling its own transform: no parent, constraints or drivers. "
            "Set its location, rotation and scale directly."
        )
    extra = sorted(name for name, obj in objects.items() if name != "Dwelling" and _solid(obj))
    if extra:
        return (
            f"Your script created {', '.join(extra)} besides the Dwelling. Only the Dwelling "
            "is measured, so join all building geometry (walls, roof, decks, eaves) into "
            "that one mesh."
        )
    return None


def _asks_is_viewport(tree: Any, seen: frozenset[str] = frozenset()) -> bool:
    """Whether a node tree, or any group inside it, has an Is Viewport node."""
    if tree is None or tree.name in seen:
        return False
    for node in tree.nodes:
        if node.bl_idname == "GeometryNodeIsViewport":
            return True
        group = getattr(node, "node_tree", None)
        if group is not None and _asks_is_viewport(group, seen | {tree.name}):
            return True
    return False


def _solid(obj: Any) -> bool:
    """Whether ``obj`` renders as something solid: not a light, camera or plain empty."""
    if obj.type == "EMPTY":
        return obj.instance_type != "NONE"
    return obj.type not in ("LIGHT", "CAMERA")


def _measure(dwelling: Any) -> dict[str, Any]:
    """Every triangle the Dwelling evaluates to, in the local frame: its mesh and
    any instances its modifiers make (e.g. Geometry Nodes), as a renderer would
    see them. The host derives the outline, walls and floor from them."""
    triangles: list[list[list[float]]] = []
    for instance in b.context.evaluated_depsgraph_get().object_instances:
        owner = instance.parent if instance.is_instance else instance.object
        if owner is None or owner.original != dwelling:
            continue
        error = _add_triangles(instance.object, instance.matrix_world.copy(), triangles)
        if error is not None:
            return {"error": error}
    return {
        "triangles": triangles,
        "floor_area_m2": _plain(dwelling.get("floor_area_m2")),
        "storeys": _plain(dwelling.get("storeys")),
    }


def _add_triangles(obj: Any, world: Any, triangles: list[list[list[float]]]) -> str | None:
    """Append ``obj``'s surface triangles, placed by ``world``; an error if too many."""
    try:
        mesh = obj.to_mesh()
    except RuntimeError:  # no surface to measure (points, volumes): nothing renders solid
        return None
    if mesh is None:
        return None
    try:
        mesh.calc_loop_triangles()
        total = len(triangles) + len(mesh.loop_triangles)
        if total > MAX_TRIANGLES:
            return TOO_DETAILED.format(n=total)
        points = [list(world @ v.co) for v in mesh.vertices]
        if not all(math.isfinite(c) for point in points for c in point):
            return NOT_FINITE
        triangles += [[points[i] for i in tri.vertices] for tri in mesh.loop_triangles]
    finally:
        obj.to_mesh_clear()
    return None


def _bake(dwelling: Any, triangles: list[list[list[float]]], look: dict[str, Any]) -> None:
    """Replace the model's Dwelling in the scene with a plain mesh of exactly the
    measured triangles in the host's opaque finishes, roof faces apart from
    walls, with UVs in metres: no modifier, instancer setting or material can
    make the render differ from what was checked."""
    b.context.scene.collection.objects.unlink(dwelling)
    dwelling.name = "Dwelling.model"
    vertices = [tuple(point) for triangle in triangles for point in triangle]
    faces = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(triangles))]
    mesh = b.data.meshes.new("Dwelling")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    parts = (look["walls"], look["roof"])  # material 0, 1
    mesh.materials.append(finishes.material("Dwelling walls", parts[0]))
    mesh.materials.append(finishes.material("Dwelling roof", parts[1]))
    _roof_apart(mesh, triangles)
    turned = [finishes.turned(part) for part in parts]
    uvs: list[float] = []
    for triangle, polygon in zip(triangles, mesh.polygons, strict=True):
        for u, v in surface_math.face_uvs(*triangle):
            uvs += (-v, u) if turned[polygon.material_index] else (u, v)
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", uvs)  # loops follow the corners
    b.context.scene.collection.objects.link(b.data.objects.new("Dwelling", mesh))


def _roof_apart(mesh: Any, triangles: list[list[list[float]]]) -> None:
    """Give roof faces material 1: level faces in the Dwelling's upper half."""
    heights = [point[2] for triangle in triangles for point in triangle]
    eaves = (min(heights, default=0.0) + max(heights, default=0.0)) / 2  # floors, decks below
    for polygon in mesh.polygons:
        level = abs(polygon.normal.z) > ROOF_NORMAL_Z
        polygon.material_index = 1 if level and polygon.center.z > eaves else 0


def _plain(value: Any) -> Any:
    """A custom property as plain JSON: numbers, strings and lists pass, anything
    else becomes its repr, so a strange value is reported rather than crashing."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if hasattr(value, "to_list"):
        return value.to_list()
    return repr(value)


if __name__ == "__main__":
    main(sys.argv)
