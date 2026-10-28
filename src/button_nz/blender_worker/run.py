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
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from button_nz.blender_worker import design_io
from button_nz.blender_worker.design_io import DID_NOT_FINISH
from button_nz.blender_worker.sandbox import SCRATCH, Sandbox
from button_nz.blender_worker.scene_input import SceneInput

BUILD_SCRIPT = Path(__file__).with_name("build_scene.py")
SCRIPT_PASS = Path(__file__).with_name("design_script.py")  # the model's script, untrusted
MEASURE_PASS = Path(__file__).with_name("design_measure.py")  # trusted measurement
MIN_FREE_GPU_MIB = 4096
RESULT_LIMIT_BYTES = 256 << 20  # the most pass 1 may send back: its design file
OUTPUT_TAIL_BYTES = 64 << 10  # Blender's output kept for error messages
TOO_BIG = "Your saved design is over {mb} MB. Keep the geometry simple."
GARBLED = "Your script wrote to the design run's results channel. Don't write to it."


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
    _run_blender(blender, BUILD_SCRIPT, [str(out.scene), str(out.glb), str(out.png)], timeout_s)
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
    sandboxed with no network (see ``sandbox``). Pass 1 can't write the host's
    disk at all: its design file comes back over a pipe, capped in size, and
    the host saves it to ``out_dir/script``. A failure caused by the model's
    work is returned as feedback in the measurements; any other failure raises
    ``BlenderError``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = out_dir / "script"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    scene_path, script_path = out_dir / "scene.json", out_dir / "design.py"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")
    for stale in ("measurements.json", "design.glb", "design.png"):
        (out_dir / stale).unlink(missing_ok=True)
    blend = scratch / "design.blend"
    error = _script_pass(blender, scene_path, script_path, blend, timeout_s)
    if error is not None:
        return DesignOutputs({"error": error}, script_path, None, None)
    return _measure_pass(blender, scene_path, blend, out_dir, timeout_s)


def _script_pass(
    blender: str, scene_path: Path, script_path: Path, blend: Path, timeout_s: float
) -> str | None:
    """Pass 1: the model's error as feedback, or None once its design is saved
    to ``blend``."""
    read_fd, write_fd = os.pipe()
    results = _Reader(read_fd, RESULT_LIMIT_BYTES, keep="head")
    sandbox = Sandbox(inputs=(scene_path, script_path), untrusted=True)
    args = [str(scene_path), str(script_path), SCRATCH, str(write_fd)]
    failure: BlenderError | None = None
    try:
        _run_blender(blender, SCRIPT_PASS, args, timeout_s, sandbox, pass_fds=(write_fd,))
    except BlenderError as error:
        failure = error
    finally:
        os.close(write_fd)
    data = results.wait()
    if results.overflowed:
        return TOO_BIG.format(mb=RESULT_LIMIT_BYTES >> 20)
    return _script_outcome(data, failure, blend)


def _script_outcome(data: bytes, failure: BlenderError | None, blend: Path) -> str | None:
    """What pass 1 reported: the script's error, None once ``blend`` is saved, or
    ``DID_NOT_FINISH`` if the script started and never got that far."""
    if not data.startswith(design_io.STARTED + bytes(8)):
        raise failure or BlenderError("pass 1 never started the model's script")
    try:
        frames = design_io.frames(data)
    except ValueError:
        return GARBLED  # only the model's script could have garbled the stream
    for kind, payload in frames[1:]:
        if kind == design_io.FAILED:
            return payload.decode("utf-8", errors="replace")
        if kind == design_io.SAVED:
            blend.write_bytes(payload)
            return None
    return DID_NOT_FINISH


def _measure_pass(
    blender: str, scene_path: Path, blend: Path, out_dir: Path, timeout_s: float
) -> DesignOutputs:
    """Pass 2: measurements, GLB and render of what pass 1 saved."""
    script_path, measurements_path = out_dir / "design.py", out_dir / "measurements.json"
    glb, png = out_dir / "design.glb", out_dir / "design.png"
    sandbox = Sandbox(inputs=(scene_path, blend), writable=out_dir, renders=True)
    args = [str(scene_path), str(blend), str(out_dir)]
    try:
        _run_blender(blender, MEASURE_PASS, args, timeout_s, sandbox)
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
    """Whether pass 2's output says it was stopped inside the model's work."""
    return os.path.lexists(path) and _read_json(path).get("error") == DID_NOT_FINISH


def _read_json(path: Path) -> Mapping[str, Any]:
    """A pass's JSON output, from a regular file only: never through a symlink,
    and never blocking on a FIFO."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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
    args: Sequence[str],
    timeout_s: float,
    sandbox: Sandbox | None = None,
    pass_fds: Sequence[int] = (),
) -> None:
    """Run ``script`` in Blender, in ``sandbox`` if given. Only the last
    ``OUTPUT_TAIL_BYTES`` of its output are kept, however much it prints."""
    command = [blender, "-b", "--factory-startup", "--python-exit-code", "1"]
    command += ["--python", str(script), "--", *args]
    env = dict(os.environ)
    gpus = _visible_gpus()
    if gpus is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpus
    if sandbox is not None:
        command = sandbox.wrap(command, env)
    read_fd, write_fd = os.pipe()
    output = _Reader(read_fd, OUTPUT_TAIL_BYTES, keep="tail")
    try:
        process = subprocess.Popen(
            command, stdout=write_fd, stderr=write_fd, env=env, pass_fds=pass_fds
        )
    except OSError as error:
        raise BlenderError(f"could not run Blender: {error}") from error
    finally:
        os.close(write_fd)
    try:
        returncode = process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise BlenderError(f"Blender ran past {timeout_s:g} s", killed=True) from None
    tail = output.wait().decode("utf-8", errors="replace")
    if returncode != 0:
        lines = "\n".join(tail.splitlines()[-30:])
        # Killed by signal n: -n, or 128 + n when bubblewrap passes it on.
        killed = returncode < 0 or returncode > 128
        raise BlenderError(f"Blender exited {returncode}:\n{lines}", killed)


class _Reader:
    """Reads a pipe to its end on a thread, keeping at most ``limit`` bytes: the
    first (``keep="head"``, closing the pipe on overflow) or the last."""

    def __init__(self, fd: int, limit: int, keep: Literal["head", "tail"]) -> None:
        self.overflowed = False
        self._fd, self._limit, self._keep = fd, limit, keep
        self._data = bytearray()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def wait(self) -> bytes:
        self._thread.join()
        return bytes(self._data)

    def _read(self) -> None:
        try:
            while chunk := os.read(self._fd, 1 << 20):
                self._data += chunk
                if len(self._data) <= self._limit:
                    continue
                if self._keep == "tail":
                    del self._data[: len(self._data) - self._limit]
                    continue
                self.overflowed = True
                return
        finally:
            os.close(self._fd)


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
