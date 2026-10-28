"""Run headless Blender to build a scene, export GLB and render a PNG.

Blender runs in a subprocess with ``--python-exit-code 1``, so a Python error
inside the build script fails the run. A run that exits 0 but leaves an output
missing also raises: a scene is never reported built when it is not.

On NVIDIA machines, Blender only sees GPUs with at least ``MIN_FREE_GPU_MIB``
free (other processes, such as a local model server, may hold a whole card),
unless ``CUDA_VISIBLE_DEVICES`` already says which to use. Without
``nvidia-smi``, the choice is Blender's own; it still fails without a GPU.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from button_nz.blender_worker.scene_input import SceneInput

BUILD_SCRIPT = Path(__file__).with_name("build_scene.py")
DESIGN_SCRIPT = Path(__file__).with_name("run_design.py")
CYCLES_CACHE = Path.home() / ".cache" / "cycles"  # compiled GPU kernels, kept across runs
MIN_FREE_GPU_MIB = 4096


class BlenderError(RuntimeError):
    """A Blender run failed."""


@dataclass(frozen=True)
class DesignOutputs:
    """One run of a design script. ``glb`` and ``png`` are None if the script failed."""

    measurements: Mapping[str, Any]
    script: Path
    glb: Path | None
    png: Path | None


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
    _run_blender(blender, BUILD_SCRIPT, [out.scene, out.glb, out.png], timeout_s)
    _require(out.glb, out.png)
    return out


def run_design(
    scene: SceneInput,
    script: str,
    out_dir: Path,
    blender: str = "blender",
    timeout_s: float = 900.0,
) -> DesignOutputs:
    """Run a model-written ``script`` in the site ``scene``, sandboxed: no network,
    and no writes outside ``out_dir`` (and Cycles' kernel cache)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_path, script_path = out_dir / "scene.json", out_dir / "design.py"
    measurements_path = out_dir / "measurements.json"
    glb, png = out_dir / "design.glb", out_dir / "design.png"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")
    for stale in (measurements_path, glb, png):
        stale.unlink(missing_ok=True)
    _run_blender(
        blender, DESIGN_SCRIPT, [scene_path, script_path, out_dir], timeout_s, writable=out_dir
    )
    _require(measurements_path)
    measurements = cast("Mapping[str, Any]", json.loads(measurements_path.read_text("utf-8")))
    if measurements.get("error"):
        return DesignOutputs(measurements, script_path, None, None)
    _require(glb, png)
    return DesignOutputs(measurements, script_path, glb, png)


def _run_blender(
    blender: str, script: Path, args: list[Path], timeout_s: float, writable: Path | None = None
) -> None:
    command = [
        blender,
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(script),
        "--",
        *(str(a) for a in args),
    ]
    if writable is not None:
        command = _sandboxed(command, writable)
    env = dict(os.environ)
    gpus = _visible_gpus()
    if gpus is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpus
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, env=env)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BlenderError(f"could not run Blender: {error}") from error
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-30:])
        raise BlenderError(f"Blender exited {result.returncode}:\n{tail}")


def _sandboxed(command: list[str], writable: Path) -> list[str]:
    """``command`` under bubblewrap: read-only filesystem except ``writable`` and
    the Cycles kernel cache, a fresh /tmp, GPU devices, and no network."""
    CYCLES_CACHE.mkdir(parents=True, exist_ok=True)
    out, cache = str(writable.resolve()), str(CYCLES_CACHE)
    return [
        "bwrap",
        "--ro-bind", "/", "/",
        "--dev-bind", "/dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", out, out,
        "--bind", cache, cache,
        "--unshare-net",
        "--unshare-pid",
        "--die-with-parent",
        "--new-session",
        "--",
        *command,
    ]  # fmt: skip


def _require(*paths: Path) -> None:
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise BlenderError(f"Blender did not write {', '.join(missing)}")


def _visible_gpus() -> str | None:
    """``CUDA_VISIBLE_DEVICES`` for Blender: as set, or every GPU with room, by
    UUID (nvidia-smi's indices follow PCI order, which CUDA's need not). None
    without NVIDIA tooling."""
    preset = os.environ.get("CUDA_VISIBLE_DEVICES")
    if preset is not None:
        return preset
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        return None
    query = [nvidia_smi, "--query-gpu=uuid,memory.free", "--format=csv,noheader,nounits"]
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
