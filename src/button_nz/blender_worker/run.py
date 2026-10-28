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
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from button_nz.blender_worker.design_io import DID_NOT_FINISH
from button_nz.blender_worker.scene_input import SceneInput

BUILD_SCRIPT = Path(__file__).with_name("build_scene.py")
SCRIPT_PASS = Path(__file__).with_name("design_script.py")  # the model's script, untrusted
MEASURE_PASS = Path(__file__).with_name("design_measure.py")  # trusted measurement
CYCLES_CACHE = Path.home() / ".cache" / "cycles"  # compiled GPU kernels, kept across runs
# A user-level Blender install (see README): the launcher and the build it runs.
BLENDER_INSTALL_PATHS = (Path.home() / ".local" / "bin", Path.home() / ".local" / "opt")
SANDBOX_ENV = ("PATH", "HOME", "LANG", "CUDA_VISIBLE_DEVICES")  # all the sandbox gets
MIN_FREE_GPU_MIB = 4096


class BlenderError(RuntimeError):
    """A Blender run failed. ``killed`` if it timed out or a signal ended it (a
    crash), rather than exiting with an error."""

    def __init__(self, message: str, killed: bool = False) -> None:
        super().__init__(message)
        self.killed = killed


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
    """Run a model-written ``script`` in the site ``scene`` (pass 1, untrusted),
    then measure, export and render what it built (pass 2, trusted). Both run
    sandboxed with no network. Pass 1 may write only to ``out_dir/script``, so
    nothing it leaves there (such as a symlink) reaches the files the host
    writes; pass 2 writes ``out_dir`` and keeps Cycles' kernel cache. A failure
    caused by the model's work is returned as feedback in the measurements; any
    other failure raises ``BlenderError``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = out_dir / "script"
    shutil.rmtree(scratch, ignore_errors=True)  # unlinks symlinks, never follows them
    scratch.mkdir()
    scene_path, script_path = out_dir / "scene.json", out_dir / "design.py"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")
    for stale in ("measurements.json", "design.glb", "design.png"):
        (out_dir / stale).unlink(missing_ok=True)
    error = _script_pass(blender, scene_path, script_path, scratch, timeout_s)
    if error is not None:
        return DesignOutputs({"error": error}, script_path, None, None)
    return _measure_pass(blender, scene_path, scratch / "design.blend", out_dir, timeout_s)


def _script_pass(
    blender: str, scene_path: Path, script_path: Path, scratch: Path, timeout_s: float
) -> str | None:
    """Pass 1: the model's error as feedback, or None once its design is saved."""
    status = scratch / "script.json"
    try:
        _run_blender(blender, SCRIPT_PASS, [scene_path, script_path, scratch], timeout_s, scratch)
    except BlenderError:
        # Only the model's script runs while script.json says it did not finish.
        if not _unfinished(status):
            raise
        return DID_NOT_FINISH
    error = _read_json(status).get("error")
    if error:
        return str(error)
    _require(scratch / "design.blend")
    return None


def _measure_pass(
    blender: str, scene_path: Path, blend: Path, out_dir: Path, timeout_s: float
) -> DesignOutputs:
    """Pass 2: measurements, GLB and render of what pass 1 saved."""
    script_path, measurements_path = out_dir / "design.py", out_dir / "measurements.json"
    glb, png = out_dir / "design.glb", out_dir / "design.png"
    args = [scene_path, blend, out_dir]
    try:
        _run_blender(blender, MEASURE_PASS, args, timeout_s, out_dir, renders=True)
    except BlenderError as error:
        # A timeout or crash while the model's geometry is measured or rendered is
        # its to fix; a Python error is this runner's, and Blender's otherwise.
        if not (error.killed and _unfinished(measurements_path)):
            raise
        for partial in (glb, png):
            partial.unlink(missing_ok=True)
        return DesignOutputs(_read_json(measurements_path), script_path, None, None)
    measurements = _read_json(measurements_path)
    if measurements.get("error"):
        return DesignOutputs(measurements, script_path, None, None)
    _require(glb, png)
    return DesignOutputs(measurements, script_path, glb, png)


def _unfinished(path: Path) -> bool:
    """Whether a pass's output file says it was stopped inside the model's work."""
    return os.path.lexists(path) and _read_json(path).get("error") == DID_NOT_FINISH


def _read_json(path: Path) -> Mapping[str, Any]:
    """A pass's JSON output, from a regular file only: never through a symlink,
    which pass 1 could point at any file the host can read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError as error:
        raise BlenderError(f"Blender did not write {path}") from error
    except OSError as error:
        raise BlenderError(f"{path.name} is not a regular file") from error
    with os.fdopen(fd, encoding="utf-8") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise BlenderError(f"{path.name} is not a regular file")
        try:
            value: object = json.load(f)
        except json.JSONDecodeError as error:
            raise BlenderError(f"{path.name} is not valid JSON") from error
    if not isinstance(value, dict):
        raise BlenderError(f"{path.name} is not a JSON object")
    return cast("Mapping[str, Any]", value)


def _run_blender(
    blender: str,
    script: Path,
    args: list[Path],
    timeout_s: float,
    writable: Path | None = None,
    renders: bool = False,
) -> None:
    """Run ``script`` in Blender; sandboxed if it may write only to ``writable``,
    with its input files in ``args`` mounted read-only, and Cycles' kernel cache
    mounted only for a pass that ``renders``."""
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
    env = dict(os.environ)
    gpus = _visible_gpus()
    if gpus is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpus
    if writable is not None:
        inputs = [a for a in args if a.is_file()]
        command = _sandboxed(command, writable, inputs, env, renders)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, env=env)
    except subprocess.TimeoutExpired as error:
        raise BlenderError(f"Blender ran past {timeout_s:g} s: {error}", killed=True) from error
    except OSError as error:
        raise BlenderError(f"could not run Blender: {error}") from error
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-30:])
        # Killed by signal n: -n, or 128 + n when bubblewrap passes it on.
        killed = result.returncode < 0 or result.returncode > 128
        raise BlenderError(f"Blender exited {result.returncode}:\n{tail}", killed)


def _sandboxed(
    command: list[str],
    writable: Path,
    inputs: list[Path],
    env: Mapping[str, str],
    renders: bool,
) -> list[str]:
    """``command`` under bubblewrap, for untrusted model-written scripts:
    read-only system files; a fresh, empty home, /tmp and /run (no host Unix
    sockets such as the user's D-Bus or Docker), with only Blender, the
    worker scripts and ``inputs`` mounted back read-only, and ``writable`` (and,
    to render, the Cycles kernel cache) read-write; a
    cleared environment (no API keys or other secrets); GPU devices; no network."""
    CYCLES_CACHE.mkdir(parents=True, exist_ok=True)
    home = str(Path.home())
    args = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc"]
    args += ["--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", home]
    for path in [*_sandbox_read_paths(command[0]), *(p.resolve() for p in inputs)]:
        args += ["--ro-bind", str(path), str(path)]
    # The kernel cache only for rendering: model code never gets to write to it.
    for path in (CYCLES_CACHE, writable.resolve()) if renders else (writable.resolve(),):
        args += ["--bind", str(path), str(path)]
    args += ["--unshare-net", "--unshare-pid", "--die-with-parent", "--new-session", "--clearenv"]
    for name in SANDBOX_ENV:
        if name in env:
            args += ["--setenv", name, env[name]]
    return [*args, "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--", *command]


def _sandbox_read_paths(blender: str) -> list[Path]:
    """The worker scripts, Blender's directory, and the user-level install
    (``~/.local/bin`` launcher and ``~/.local/opt`` build) if they exist."""
    paths = [BUILD_SCRIPT.parent.resolve()]
    found = shutil.which(blender)
    if found:
        paths.append(Path(found).resolve().parent)
    paths += [p for p in BLENDER_INSTALL_PATHS if p.is_dir()]
    return list(dict.fromkeys(paths))


def _require(*paths: Path) -> None:
    missing = [str(p) for p in paths if p.is_symlink() or not p.is_file()]
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
