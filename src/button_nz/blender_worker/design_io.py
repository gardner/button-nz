"""Shared by the two Blender passes of a design run (``design_script.py`` and
``design_measure.py``). Runs inside Blender's Python: standard library only.

While the model's work is running, measured or rendered, a pass's JSON output
says ``DID_NOT_FINISH``. If Blender dies there, that note is what remains, and
it comes back to the model as feedback. Writes are atomic, so a pass killed
mid-write leaves the previous complete file, never a truncated one.
"""

import json
import os
from typing import Any

SITE_OBJECTS = ("Terrain", "AboveGround", "Camera", "Sun")
DID_NOT_FINISH = (
    "Blender did not finish with your design: it ran past the time limit or crashed while "
    "running your script, measuring the Dwelling or rendering it. Keep the geometry simple."
)


def site_names(scene: dict[str, Any]) -> set[str]:
    """The objects ``build_scene.build`` makes for ``scene``."""
    return {*SITE_OBJECTS, *(f"Parcel.{i}" for i in range(len(scene["parcels"])))}


def write_json(path: str, value: dict[str, Any]) -> None:
    partial = f"{path}.partial"
    with open(partial, "w", encoding="utf-8") as f:
        json.dump(value, f)
    os.replace(partial, path)
