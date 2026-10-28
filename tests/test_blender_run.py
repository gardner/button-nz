"""Tests for button_nz.blender_worker.run with a stand-in `blender` executable."""

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from button_nz.blender_worker import run
from button_nz.blender_worker.design_io import DID_NOT_FINISH
from button_nz.blender_worker.run import BUILD_SCRIPT, BlenderError, build_scene, run_design
from button_nz.blender_worker.scene_input import SceneInput

# Records its arguments; writes the GLB and PNG it was given unless told not to.
FAKE_BLENDER = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$(dirname "$0")/args"
printf '%s' "${CUDA_VISIBLE_DEVICES-unset}" > "$(dirname "$0")/gpus"
outputs=("${@: -2}")
if [[ -z "$FAKE_SKIP_OUTPUT" ]]; then
  printf 'glTF' > "${outputs[0]}"
  printf 'png' > "${outputs[1]}"
fi
echo "Traceback: boom" >&2
exit "${FAKE_EXIT:-0}"
"""

SCENE: SceneInput = {
    "frame": {
        "origin_nztm": [1.0, 2.0],
        "crs": "EPSG:2193",
        "vertical_crs": "EPSG:7839",
        "datum_m": 0.0,
    },
    "terrain": {"rows": 1, "cols": 1, "cell_m": 1.0, "x0": 0.0, "y0": 0.0, "heights": [0.0]},
    "ndsm": {"rows": 1, "cols": 1, "cell_m": 1.0, "x0": 0.0, "y0": 0.0, "heights": [0.0]},
    "parcels": [],
    "sources": [],
}


# GPUs are chosen by UUID: nvidia-smi's indices (PCI order) need not match
# CUDA's device order. BUSY is nearly full (another process); FREE is idle.
BUSY = "GPU-11111111-1111-1111-1111-111111111111"
FREE = "GPU-22222222-2222-2222-2222-222222222222"
FAKE_NVIDIA_SMI = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$(dirname "$0")/nvidia-smi-args"
cat "$(dirname "$0")/gpu-memory"
"""


@pytest.fixture
def blender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("blender", FAKE_BLENDER), ("nvidia-smi", FAKE_NVIDIA_SMI)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "gpu-memory").write_text(f"{BUSY}, 1789\n{FREE}, 32605\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    return bin_dir / "blender"


def test_only_gpus_with_free_memory_are_visible(tmp_path: Path, blender: Path) -> None:
    build_scene(SCENE, tmp_path / "out", blender=str(blender))
    assert (blender.parent / "gpus").read_text(encoding="utf-8") == FREE
    query = (blender.parent / "nvidia-smi-args").read_text(encoding="utf-8").splitlines()
    assert "--query-gpu=uuid,memory.free" in query


def test_a_preset_gpu_choice_is_respected(
    tmp_path: Path, blender: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    build_scene(SCENE, tmp_path / "out", blender=str(blender))
    assert (blender.parent / "gpus").read_text(encoding="utf-8") == "0"


def test_no_gpu_with_room_raises(tmp_path: Path, blender: Path) -> None:
    (blender.parent / "gpu-memory").write_text(f"{BUSY}, 1789\n{FREE}, 512\n", encoding="utf-8")
    with pytest.raises(BlenderError, match="GiB free"):
        build_scene(SCENE, tmp_path / "out", blender=str(blender))


def test_runs_the_build_script_headless(tmp_path: Path, blender: Path) -> None:
    out = build_scene(SCENE, tmp_path / "out", blender=str(blender))
    args = (blender.parent / "args").read_text(encoding="utf-8").splitlines()
    assert args[:4] == ["-b", "--factory-startup", "--python-exit-code", "1"]
    assert args[args.index("--python") + 1] == str(BUILD_SCRIPT)
    assert args[args.index("--") + 1 :] == [str(out.scene), str(out.glb), str(out.png)]
    assert json.loads(out.scene.read_text(encoding="utf-8")) == SCENE
    assert out.glb.read_bytes() == b"glTF"


def test_a_failed_run_raises_with_blenders_output(
    tmp_path: Path, blender: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_EXIT", "1")
    with pytest.raises(BlenderError, match="Traceback: boom"):
        build_scene(SCENE, tmp_path / "out", blender=str(blender))


def test_a_run_that_writes_no_output_raises(
    tmp_path: Path, blender: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SKIP_OUTPUT", "1")
    with pytest.raises(BlenderError, match="did not write"):
        build_scene(SCENE, tmp_path / "out", blender=str(blender))


def test_the_build_script_exists() -> None:
    assert BUILD_SCRIPT.is_file()


def test_without_nvidia_smi_gpu_choice_is_left_to_blender(
    tmp_path: Path, blender: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_command(_: str) -> None:
        return None

    monkeypatch.setattr("button_nz.blender_worker.run.shutil.which", no_command)
    build_scene(SCENE, tmp_path / "out", blender=str(blender))
    assert (blender.parent / "gpus").read_text(encoding="utf-8") == "unset"


# Stands in for both passes of a design run: pass 1 reports over its results
# pipe as the `mode` file says; pass 2 notes that the model's geometry was being
# measured and then crashes, as a segfault in runaway geometry would.
FAKE_PASSES = """#!/usr/bin/env python3
import os, signal, sys
args = sys.argv[sys.argv.index("--") + 1 :]
here = os.path.dirname(os.path.abspath(__file__))
mode = open(os.path.join(here, "mode")).read().strip()
if any(a.endswith("design_script.py") for a in sys.argv):
    out = os.fdopen(int(args[-1]), "wb")
    def send(kind, payload=b""):
        out.write(kind + len(payload).to_bytes(8, "big") + payload)
        out.flush()
    send(b"S")
    if mode == "huge":
        send(b"B", b"x" * 4096)
    elif mode == "garbled":
        out.write(b"junk")
    else:
        send(b"B", b"blend")
else:
    unfinished = open(os.path.join(here, "unfinished.json")).read()
    open(os.path.join(args[-1], "measurements.json"), "w").write(unfinished)
    os.kill(os.getpid(), signal.SIGSEGV)
"""


@pytest.fixture
def passes(blender: Path) -> Path:
    blender.write_text(FAKE_PASSES, encoding="utf-8")
    (blender.parent / "unfinished.json").write_text(
        json.dumps({"error": DID_NOT_FINISH}), encoding="utf-8"
    )
    (blender.parent / "mode").write_text("save", encoding="utf-8")
    return blender


@pytest.mark.blender  # needs bubblewrap, as every design run does
def test_a_crash_while_measuring_in_the_sandbox_is_the_models_feedback(
    tmp_path: Path, passes: Path
) -> None:
    """bwrap reports a child killed by signal n as exit 128 + n, not -n."""
    out = run_design(SCENE, "x = 1\n", tmp_path / "run", blender=str(passes))
    assert out.measurements["error"] == DID_NOT_FINISH
    assert out.glb is None and out.png is None


@pytest.mark.blender
def test_a_design_file_over_the_limit_is_feedback(
    tmp_path: Path, passes: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "RESULT_LIMIT_BYTES", 1024)
    (passes.parent / "mode").write_text("huge", encoding="utf-8")
    out = run_design(SCENE, "x = 1\n", tmp_path / "run", blender=str(passes))
    assert "Keep the geometry simple" in str(out.measurements["error"])
    assert not (tmp_path / "run" / "script" / "design.blend").exists()


@pytest.mark.blender
def test_garbled_results_are_the_models_feedback(tmp_path: Path, passes: Path) -> None:
    (passes.parent / "mode").write_text("garbled", encoding="utf-8")
    out = run_design(SCENE, "x = 1\n", tmp_path / "run", blender=str(passes))
    assert "results channel" in str(out.measurements["error"])


def _finished_then(tmp_path: Path, failure: BlenderError, measured: Mapping[str, object]):
    """A pass 2 that writes ``measured``, the GLB, the render and half a mask,
    then fails with ``failure`` (as if the silhouette render crashed or timed out)."""

    def fake(
        blender: str, script: Path, args: list[str], timeout_s: float, sandbox: object
    ) -> None:
        out = Path(args[2])
        (out / "measurements.json").write_text(json.dumps(measured), encoding="utf-8")
        for name in ("design.glb", "design.png", run.MASK):
            (out / name).write_bytes(b"partial" if name == run.MASK else b"done")
        raise failure

    return fake


@pytest.mark.parametrize("failure", [BlenderError("killed", killed=True), BlenderError("exit 1")])
def test_a_failed_silhouette_keeps_the_finished_design(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: BlenderError
) -> None:
    """The design was measured, exported and rendered: only the optional mask is lost."""
    monkeypatch.setattr(run, "_run_blender", _finished_then(tmp_path, failure, {"error": None}))
    outputs = run._measure_pass("blender", tmp_path / "s.json", tmp_path / "d.blend", tmp_path, 60)  # pyright: ignore[reportPrivateUsage]
    assert outputs.measurements["error"] is None
    assert outputs.glb is not None and outputs.png is not None
    assert outputs.mask is None and not (tmp_path / run.MASK).exists()


def test_a_crash_before_the_design_is_finished_is_still_the_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unfinished = {"error": DID_NOT_FINISH}
    killed = BlenderError("killed", killed=True)
    monkeypatch.setattr(run, "_run_blender", _finished_then(tmp_path, killed, unfinished))
    outputs = run._measure_pass("blender", tmp_path / "s.json", tmp_path / "d.blend", tmp_path, 60)  # pyright: ignore[reportPrivateUsage]
    assert outputs.measurements["error"] == DID_NOT_FINISH and outputs.glb is None
