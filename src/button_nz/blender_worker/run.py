"""Run headless Blender to build a scene, export GLB and render a PNG.

Blender runs in a subprocess with ``--python-exit-code 1``, so a Python error
inside the build script fails the run. A run that exits 0 but leaves an output
missing also raises: a scene is never reported built when it is not.

Blender only sees GPUs with at least ``MIN_FREE_GPU_MIB`` free (other
processes, such as a local model server, may hold a whole card), unless
``CUDA_VISIBLE_DEVICES`` already says which to use.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from button_nz.blender_worker.scene_input import SceneInput

BUILD_SCRIPT = Path(__file__).with_name("build_scene.py")
MIN_FREE_GPU_MIB = 4096


class BlenderError(RuntimeError):
    """A Blender run failed."""


@dataclass(frozen=True)
class SceneOutputs:
    scene: Path
    glb: Path
    png: Path


def build_scene(
    scene: SceneInput,
    out_dir: Path,
    blender: str = "blender",
    timeout_s: float = 900.0,
) -> SceneOutputs:
    """Build ``scene`` in headless Blender, writing JSON, GLB and PNG to ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = SceneOutputs(out_dir / "scene.json", out_dir / "scene.glb", out_dir / "scene.png")
    out.scene.write_text(json.dumps(scene), encoding="utf-8")
    for stale in (out.glb, out.png):
        stale.unlink(missing_ok=True)
    command = [
        blender,
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(BUILD_SCRIPT),
        "--",
        str(out.scene),
        str(out.glb),
        str(out.png),
    ]
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": _visible_gpus()}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BlenderError(f"could not run Blender: {error}") from error
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-30:])
        raise BlenderError(f"Blender exited {result.returncode}:\n{tail}")
    missing = [str(p) for p in (out.glb, out.png) if not p.is_file()]
    if missing:
        raise BlenderError(f"Blender did not write {', '.join(missing)}")
    return out


def _visible_gpus() -> str:
    """``CUDA_VISIBLE_DEVICES`` for Blender: as set, or every GPU with room, by
    UUID (nvidia-smi's indices follow PCI order, which CUDA's need not)."""
    preset = os.environ.get("CUDA_VISIBLE_DEVICES")
    if preset is not None:
        return preset
    query = ["nvidia-smi", "--query-gpu=uuid,memory.free", "--format=csv,noheader,nounits"]
    try:
        listing = subprocess.run(query, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise BlenderError(f"could not list GPUs with nvidia-smi: {error}") from error
    free = [
        uuid
        for uuid, mib in (line.split(",") for line in listing.strip().splitlines())
        if int(mib) >= MIN_FREE_GPU_MIB
    ]
    if not free:
        raise BlenderError(f"no GPU has {MIN_FREE_GPU_MIB // 1024} GiB free:\n{listing}")
    return ",".join(uuid.strip() for uuid in free)
