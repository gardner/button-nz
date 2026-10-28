"""Pass 1 of a design run: the model's script, untrusted. Run sandboxed by
``button_nz.blender_worker.run.run_design``:

    blender -b --factory-startup --python-exit-code 1 --python design_script.py \\
        -- scene.json design.py OUT_DIR

Builds the site so the script can see it, runs the script as ``__main__``
with ``bpy``, ``math`` and ``scene`` (the scene JSON, including the terrain
heights), and saves the result as ``OUT_DIR/design.blend``. Nothing here is
trusted afterwards: pass 2 (``design_measure.py``) rebuilds the site and takes
only the model's objects from that file.

Writes ``OUT_DIR/script.json``: ``{"error": null}``, or the script's traceback
(an exception or ``exit()``) for the model to fix.
"""

import math
import os
import sys
import traceback
from typing import Any

import bpy  # pyright: ignore[reportMissingImports]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scene as _build_scene  # noqa: E402  # pyright: ignore[reportMissingImports]
import design_io as _design_io  # noqa: E402  # pyright: ignore[reportMissingImports]

b: Any = bpy  # no type stubs inside Blender
build_scene: Any = _build_scene
design_io: Any = _design_io
SCRIPT_NAME = "design.py"
SCRIPT_ENDINGS = (Exception, SystemExit)  # a tuple: Blender's Python predates PEP 758


def main(argv: list[str]) -> None:
    scene_path, script_path, out_dir = argv[argv.index("--") + 1 :]
    scene: dict[str, Any] = build_scene.load(scene_path)
    build_scene.build(scene)
    with open(script_path, encoding="utf-8") as f:
        source = f.read()
    status = os.path.join(out_dir, "script.json")
    design_io.write_json(status, {"error": design_io.DID_NOT_FINISH})
    try:
        code = compile(source, SCRIPT_NAME, "exec")
        exec(code, {"__name__": "__main__", "bpy": bpy, "math": math, "scene": scene})  # noqa: S102
    except SCRIPT_ENDINGS:  # the model's error is feedback, not a crash
        design_io.write_json(status, {"error": _script_traceback()})
        return
    b.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "design.blend"))
    design_io.write_json(status, {"error": None})


def _script_traceback() -> str:
    """The traceback from the model's script onwards, without this runner's frames."""
    lines = traceback.format_exc().splitlines()
    start = next((i for i, line in enumerate(lines) if f'"{SCRIPT_NAME}"' in line), 1)
    return "\n".join(["Traceback (most recent call last):", *lines[start:]])


if __name__ == "__main__":
    main(sys.argv)
