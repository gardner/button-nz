"""Pass 1 of a design run: the model's script, untrusted. Run sandboxed by
``button_nz.blender_worker.run.run_design``:

    blender -b --factory-startup --python-exit-code 1 --python design_script.py \\
        -- scene.json design.py SCRATCH_DIR RESULTS_FD

Builds the site so the script can see it, runs the script as ``__main__``
with ``bpy``, ``math`` and ``scene`` (the scene JSON, including the terrain
heights), and saves the result in ``SCRATCH_DIR``, a size-limited tmpfs that
vanishes with the sandbox. Nothing here is trusted afterwards: pass 2
(``design_measure.py``) rebuilds the site and takes only the model's objects
from that file.

Reports on pipe ``RESULTS_FD`` (see ``design_io``): ``STARTED``, then the
script's traceback (an exception or ``exit()``) for the model to fix, or the
saved design file.
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
    scene_path, script_path, scratch, results_fd = argv[argv.index("--") + 1 :]
    results = os.fdopen(int(results_fd), "wb", buffering=0)
    scene: dict[str, Any] = build_scene.load(scene_path)
    build_scene.build(scene)
    with open(script_path, encoding="utf-8") as f:
        source = f.read()
    design_io.send(results, design_io.STARTED)
    try:
        code = compile(source, SCRIPT_NAME, "exec")
        exec(code, {"__name__": "__main__", "bpy": bpy, "math": math, "scene": scene})  # noqa: S102
    except SCRIPT_ENDINGS:  # the model's error is feedback, not a crash
        design_io.send(results, design_io.FAILED, _script_traceback().encode())
        return
    blend = os.path.join(scratch, "design.blend")
    b.ops.wm.save_as_mainfile(filepath=blend)
    with open(blend, "rb") as f:
        design_io.send(results, design_io.SAVED, f.read())


def _script_traceback() -> str:
    """The traceback from the model's script onwards, without this runner's frames."""
    lines = traceback.format_exc().splitlines()
    start = next((i for i, line in enumerate(lines) if f'"{SCRIPT_NAME}"' in line), 1)
    return "\n".join(["Traceback (most recent call last):", *lines[start:]])


if __name__ == "__main__":
    main(sys.argv)
