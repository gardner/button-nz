"""Real sandboxed Blender runs of model-written design scripts.
Excluded by default; run with `pytest -m blender`."""

from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.proposal import parse_measurements
from button_nz.blender_worker.run import run_design
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender

BOX = """
bpy.ops.mesh.primitive_cube_add(size=1, location=(2.0, 1.0, 1.8))
dwelling = bpy.context.active_object
dwelling.name = "Dwelling"
dwelling.scale = (6.0, 5.0, 3.6)
dwelling["floor_area_m2"] = 26.0
dwelling["storeys"] = 1
"""


@pytest.fixture
def scene() -> SceneInput:
    dem = np.full((40, 50), 10.0)
    grid = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    return scene_input(grid, LocalFrame.centred_on(grid.bbox), [])


def test_a_dwelling_is_measured_exported_and_rendered(tmp_path: Path, scene: SceneInput) -> None:
    out = run_design(scene, BOX, tmp_path)
    measured = parse_measurements(out.measurements)
    assert measured.error is None
    assert measured.parts == 1
    assert measured.footprint is not None
    xs = [x for x, _ in measured.footprint]
    ys = [y for _, y in measured.footprint]
    assert (min(xs), max(xs), min(ys), max(ys)) == pytest.approx((-1.0, 5.0, -1.5, 3.5))
    assert (measured.z_min, measured.z_max) == pytest.approx((0.0, 3.6))
    assert (measured.floor_area_m2, measured.storeys) == (26.0, 1)
    assert out.glb is not None and out.glb.stat().st_size > 0
    assert out.png is not None and out.png.stat().st_size > 0


def test_a_script_error_comes_back_as_feedback(tmp_path: Path, scene: SceneInput) -> None:
    out = run_design(scene, "x = 1\nbpyy.ops.mesh.primitive_cube_add()\n", tmp_path)
    error = str(out.measurements["error"])
    assert 'File "design.py", line 2' in error
    assert "NameError" in error
    assert out.glb is None and out.png is None


def test_the_script_cannot_write_outside_its_directory(tmp_path: Path, scene: SceneInput) -> None:
    escape = Path.home() / ".button-nz-sandbox-escape-test"
    script = f"open({str(escape)!r}, 'w').write('x')\nopen('/usr/escape', 'w')\n"
    out = run_design(scene, script, tmp_path)
    assert "Read-only file system" in str(out.measurements["error"])  # system paths
    assert not escape.exists()  # the home it sees is an empty tmpfs, gone afterwards


def test_the_script_has_no_network(tmp_path: Path, scene: SceneInput) -> None:
    script = "import urllib.request\nurllib.request.urlopen('https://example.com', timeout=5)\n"
    out = run_design(scene, script, tmp_path)
    assert "URLError" in str(out.measurements["error"])


def test_the_script_cannot_read_the_home_directory_or_secrets(
    tmp_path: Path, scene: SceneInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = Path.home() / ".button-nz-sandbox-secret-test"
    secret.write_text("hunter2", encoding="utf-8")
    monkeypatch.setenv("BUTTON_NZ_TEST_SECRET", "hunter2")
    try:
        script = (
            "import os\n"
            f"leak = os.environ.get('BUTTON_NZ_TEST_SECRET', 'none')\n"
            f"leak += '|' + open({str(secret)!r}).read()\n"
        )
        out = run_design(scene, script, tmp_path)
    finally:
        secret.unlink()
    error = str(out.measurements["error"])
    assert "FileNotFoundError" in error
    assert "hunter2" not in error


def test_a_script_that_clears_the_scene_gets_feedback(tmp_path: Path, scene: SceneInput) -> None:
    clear = "for obj in list(bpy.data.objects):\n    if obj.name != 'Dwelling':\n"
    script = BOX + "\n" + clear + "        bpy.data.objects.remove(obj)\n"
    out = run_design(scene, script, tmp_path)
    assert "site" in str(out.measurements["error"])
    assert out.measurements["faces_xy"]  # measured before export failed
    assert out.glb is None and out.png is None


def test_a_main_guarded_script_runs(tmp_path: Path, scene: SceneInput) -> None:
    body = "\n".join("    " + line for line in BOX.strip().splitlines())
    script = f"def main():\n{body}\n\nif __name__ == '__main__':\n    main()\n"
    out = run_design(scene, script, tmp_path)
    assert out.measurements["error"] is None
    assert out.measurements["faces_xy"]
