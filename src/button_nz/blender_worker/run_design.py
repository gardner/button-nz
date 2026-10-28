"""Run a model-written design script in the site scene and measure the result.

Run by ``button_nz.blender_worker.run.run_design`` (inside a sandbox):

    blender -b --factory-startup --python-exit-code 1 --python run_design.py \\
        -- scene.json design.py OUT_DIR

The scene contract the script must meet: create one mesh object named
``Dwelling`` in the local frame (metres; x east, y north, z up; heights relative
to the scene datum). It may set ``Dwelling["floor_area_m2"]`` (internal floor
area) and ``Dwelling["storeys"]``. The script sees ``bpy``, ``math`` and
``scene`` (the scene JSON, including the terrain heights).

Writes ``OUT_DIR/measurements.json``, then (if the script ran) ``design.glb``
and ``design.png``. An exception in the script, or an export or render that
fails because the script broke the site, is recorded in the measurements for
the model to fix; it does not fail the run. The script runs as ``__main__``.
"""

import json
import math
import os
import sys
import traceback
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scene as _build_scene  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
build_scene: Any = _build_scene
SCRIPT_NAME = "design.py"
SITE_OBJECTS = ("Terrain", "AboveGround", "Camera", "Sun")


def main(argv: list[str]) -> None:
    scene_path, script_path, out_dir = argv[argv.index("--") + 1 :]
    scene: dict[str, Any] = build_scene.load(scene_path)
    build_scene.build(scene)
    with open(script_path, encoding="utf-8") as f:
        source = f.read()
    measurements: dict[str, Any] = {"error": None}
    try:
        code = compile(source, SCRIPT_NAME, "exec")
        exec(code, {"__name__": "__main__", "bpy": bpy, "math": math, "scene": scene})  # noqa: S102
    except Exception:  # the model's error is feedback, not a crash
        measurements["error"] = _script_traceback()
        _write(out_dir, measurements)
        return
    measurements |= _measure()
    _write(out_dir, measurements)  # kept even if the export below fails
    removed = [name for name in SITE_OBJECTS if b.data.objects.get(name) is None]
    if removed or b.context.scene.camera is None:
        # Blender exits on a render with no camera rather than raising, so check first.
        _fail(out_dir, measurements, f"the script removed {', '.join(removed) or 'the camera'}")
        return
    glb, png = os.path.join(out_dir, "design.glb"), os.path.join(out_dir, "design.png")
    try:
        build_scene.export(glb, png)
    except Exception as error:
        for path in (glb, png):
            if os.path.exists(path):
                os.remove(path)
        _fail(out_dir, measurements, str(error))


def _fail(out_dir: str, measurements: dict[str, Any], reason: str) -> None:
    measurements["error"] = (
        f"Exporting or rendering the scene failed: {reason}. Do not delete or change the "
        "site objects (Terrain, AboveGround, Parcel.*, Camera, Sun); only add the Dwelling."
    )
    _write(out_dir, measurements)


def _write(out_dir: str, measurements: dict[str, Any]) -> None:
    with open(os.path.join(out_dir, "measurements.json"), "w", encoding="utf-8") as f:
        json.dump(measurements, f)


def _plain(value: Any) -> Any:
    """A custom property as plain JSON: numbers, strings and lists pass, anything
    else becomes its repr, so a strange value is reported rather than crashing."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if hasattr(value, "to_list"):
        return value.to_list()
    return repr(value)


def _script_traceback() -> str:
    """The traceback from the model's script onwards, without this runner's frames."""
    lines = traceback.format_exc().splitlines()
    start = next((i for i, line in enumerate(lines) if f'"{SCRIPT_NAME}"' in line), 1)
    return "\n".join(["Traceback (most recent call last):", *lines[start:]])


def _measure() -> dict[str, Any]:
    obj = b.data.objects.get("Dwelling")
    if obj is None or obj.type != "MESH":
        return {}
    evaluated = obj.evaluated_get(b.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        points = [obj.matrix_world @ v.co for v in mesh.vertices]
        faces = [[[points[i].x, points[i].y] for i in poly.vertices] for poly in mesh.polygons]
    finally:
        evaluated.to_mesh_clear()
    if not points:
        return {}
    return {
        "faces_xy": faces,
        "z_min": min(p.z for p in points),
        "z_max": max(p.z for p in points),
        "floor_area_m2": _plain(obj.get("floor_area_m2")),
        "storeys": _plain(obj.get("storeys")),
    }


if __name__ == "__main__":
    main(sys.argv)
