"""Tests for button_nz.blender_worker.run with a stand-in `blender` executable."""

import json
import os
from pathlib import Path

import pytest

from button_nz.blender_worker.run import BUILD_SCRIPT, BlenderError, build_scene
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


# GPU 0 is nearly full (another process), GPU 1 is free.
FAKE_NVIDIA_SMI = """#!/usr/bin/env bash
cat "$(dirname "$0")/gpu-memory"
"""


@pytest.fixture
def blender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("blender", FAKE_BLENDER), ("nvidia-smi", FAKE_NVIDIA_SMI)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "gpu-memory").write_text("0, 1789\n1, 32605\n", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    return bin_dir / "blender"


def test_only_gpus_with_free_memory_are_visible(tmp_path: Path, blender: Path) -> None:
    build_scene(SCENE, tmp_path / "out", blender=str(blender))
    assert (blender.parent / "gpus").read_text(encoding="utf-8") == "1"


def test_a_preset_gpu_choice_is_respected(
    tmp_path: Path, blender: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    build_scene(SCENE, tmp_path / "out", blender=str(blender))
    assert (blender.parent / "gpus").read_text(encoding="utf-8") == "0"


def test_no_gpu_with_room_raises(tmp_path: Path, blender: Path) -> None:
    (blender.parent / "gpu-memory").write_text("0, 1789\n1, 512\n", encoding="utf-8")
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
