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


def main(argv: list[str]) -> None:
    scene_path, blend_path, out_dir = argv[argv.index("--") + 1 :]
    scene: dict[str, Any] = build_scene.load(scene_path)
    build_scene.build(scene)
    build_scene.use_gpu(b.context.scene)
    path = os.path.join(out_dir, "measurements.json")
    design_io.write_json(path, {"error": design_io.DID_NOT_FINISH})
    objects = _load(blend_path, design_io.site_names(scene))
    error = _broken_contract(objects)
    if error is not None:
        design_io.write_json(path, {"error": error})
        return
    dwelling = objects["Dwelling"]
    b.context.scene.collection.objects.link(dwelling)
    measurements = {"error": None, **_measure(dwelling)}
    design_io.write_json(path, measurements | {"error": design_io.DID_NOT_FINISH})
    build_scene.export(os.path.join(out_dir, "design.glb"), os.path.join(out_dir, "design.png"))
    design_io.write_json(path, measurements)


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
    evaluated = dwelling.evaluated_get(b.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        world = evaluated.matrix_world
        points = [world @ v.co for v in mesh.vertices]
        faces = [[[points[i].x, points[i].y] for i in poly.vertices] for poly in mesh.polygons]
    finally:
        evaluated.to_mesh_clear()
    if not points:
        return {}
    return {
        "faces_xy": faces,
        "z_min": min(p.z for p in points),
        "z_max": max(p.z for p in points),
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
