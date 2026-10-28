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

Writes ``OUT_DIR/measurements.json``, then ``design.glb`` and ``design.png``.
A broken contract is recorded in the measurements for the model to fix.
"""

import os
import sys
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scene as _build_scene  # noqa: E402  # pyright: ignore[reportMissingImports]
import design_io as _design_io  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
build_scene: Any = _build_scene
design_io: Any = _design_io
MAX_TRIANGLES = 200_000
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
    _show(dwelling)
    measurements = {"error": None} | _measure(dwelling)
    if measurements["error"] is not None:  # e.g. too detailed: don't render it either
        design_io.write_json(path, measurements)
        return
    design_io.write_json(path, measurements | {"error": design_io.DID_NOT_FINISH})
    build_scene.export(os.path.join(out_dir, "design.glb"), os.path.join(out_dir, "design.png"))
    design_io.write_json(path, measurements)


def _show(dwelling: Any) -> None:
    """Make the Dwelling, and its modifiers, evaluate as they render: what is
    checked is what is shown (the measuring depsgraph uses viewport settings)."""
    dwelling.hide_render = False
    dwelling.hide_viewport = False
    dwelling.visible_camera = True
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


def _solid(obj: Any) -> bool:
    """Whether ``obj`` renders as something solid: not a light, camera or plain empty."""
    if obj.type == "EMPTY":
        return obj.instance_type != "NONE"
    return obj.type not in ("LIGHT", "CAMERA")


def _measure(dwelling: Any) -> dict[str, Any]:
    """The Dwelling's triangles in the local frame (the host derives its outline,
    walls and floor from them) and its stated properties."""
    evaluated = dwelling.evaluated_get(b.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        if len(mesh.loop_triangles) > MAX_TRIANGLES:
            return {"error": TOO_DETAILED.format(n=len(mesh.loop_triangles))}
        world = evaluated.matrix_world
        points = [list(world @ v.co) for v in mesh.vertices]
        triangles = [[points[i] for i in tri.vertices] for tri in mesh.loop_triangles]
    finally:
        evaluated.to_mesh_clear()
    return {
        "triangles": triangles,
        "floor_area_m2": _plain(dwelling.get("floor_area_m2")),
        "storeys": _plain(dwelling.get("storeys")),
    }


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
