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
    out = run_design(scene, f"open({str(escape)!r}, 'w').write('x')\n", tmp_path)
    assert "Read-only file system" in str(out.measurements["error"])
    assert not escape.exists()


def test_the_script_has_no_network(tmp_path: Path, scene: SceneInput) -> None:
    script = "import urllib.request\nurllib.request.urlopen('https://example.com', timeout=5)\n"
    out = run_design(scene, script, tmp_path)
    assert "URLError" in str(out.measurements["error"])
