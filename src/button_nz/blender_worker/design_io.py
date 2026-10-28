"""Shared by the two Blender passes of a design run (``design_script.py`` and
``design_measure.py``) and the host. Standard library only: it runs inside
Blender's Python too.

Pass 1 (untrusted) writes nothing to the host's disk. It reports over a pipe,
in frames: ``STARTED`` before the model's script runs, then ``FAILED`` (its
traceback) or ``SAVED`` (the design file). A pass that started and sent
neither did not finish: a timeout or crash in the model's script.

While pass 2 measures or renders the model's geometry, its JSON output says
``DID_NOT_FINISH``. If Blender dies there, that note is what remains, and it
comes back to the model as feedback. Writes are atomic, so a pass killed
mid-write leaves the previous complete file, never a truncated one.
"""

import json
import os
from typing import Any, BinaryIO

STARTED, FAILED, SAVED = b"S", b"E", b"B"
_LENGTH_BYTES = 8

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


def send(stream: BinaryIO, kind: bytes, payload: bytes = b"") -> None:
    stream.write(kind + len(payload).to_bytes(_LENGTH_BYTES, "big") + payload)
    stream.flush()


def frames(data: bytes) -> list[tuple[bytes, bytes]]:
    """The frames in ``data``; ValueError if it isn't a whole number of frames."""
    found: list[tuple[bytes, bytes]] = []
    at = 0
    while at < len(data):
        header_end = at + 1 + _LENGTH_BYTES
        if header_end > len(data):
            raise ValueError("a frame header is cut short")
        length = int.from_bytes(data[at + 1 : header_end], "big")
        if header_end + length > len(data):
            raise ValueError("a frame is cut short")
        found.append((data[at : at + 1], data[header_end : header_end + length]))
        at = header_end + length
    return found
