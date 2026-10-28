"""Real sandboxed Blender runs of model-written design scripts.
Excluded by default; run with `pytest -m blender`."""

import os
from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.proposal import parse_measurements
from button_nz.blender_worker.run import BlenderError, run_design
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


_DEM = np.full((40, 50), 10.0)
_GRID = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, _DEM, np.zeros_like(_DEM), ("synthetic",))


@pytest.fixture
def scene() -> SceneInput:
    return scene_input(_GRID, LocalFrame.centred_on(_GRID.bbox), [])


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


def test_changes_to_the_site_are_discarded(tmp_path: Path, scene: SceneInput) -> None:
    """The site is rebuilt for measuring: a script can't hide or move it."""
    clear = "for obj in list(bpy.data.objects):\n    if obj.name != 'Dwelling':\n"
    script = BOX + "\n" + clear + "        bpy.data.objects.remove(obj)\n"
    out = run_design(scene, script, tmp_path)
    assert out.measurements["error"] is None
    assert out.glb is not None and b"Terrain" in out.glb.read_bytes()


def test_the_script_cannot_fake_its_measurements(tmp_path: Path, scene: SceneInput) -> None:
    fake = (
        "import json, os, sys, __main__\n"
        "here = os.path.dirname(sys.argv[sys.argv.index('--') + 1])\n"
        "tiny = {'error': None, 'faces_xy': [[[0, 0], [1, 0], [1, 1]]], 'z_min': 0, 'z_max': 1}\n"
        "try:\n"
        "    open(here + '/measurements.json', 'w').write(json.dumps(tiny))\n"
        "except OSError:\n"
        "    pass\n"
        "__main__.__dict__['_measure'] = lambda *a: tiny\n"
    )
    out = run_design(scene, BOX + fake, tmp_path)
    measured = parse_measurements(out.measurements)
    assert measured.footprint is not None
    xs = [x for x, _ in measured.footprint]
    assert (min(xs), max(xs)) == pytest.approx((-1.0, 5.0))  # the box, not the fake


def test_a_dwelling_without_its_own_transform_gets_feedback(
    tmp_path: Path, scene: SceneInput
) -> None:
    constrained = "dwelling.constraints.new('COPY_LOCATION')\n"
    out = run_design(scene, BOX + constrained, tmp_path)
    assert "constraints" in str(out.measurements["error"])
    assert out.glb is None and out.png is None


def test_an_unlinked_dwelling_gets_feedback(tmp_path: Path, scene: SceneInput) -> None:
    unlinked = (
        "mesh = bpy.data.meshes.new('D')\n"
        "mesh.from_pydata([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 3)], [], [(0, 1, 2, 3)])\n"
        "bpy.data.objects.new('Dwelling', mesh).location = (2.0, 1.0, 0.0)\n"
    )
    out = run_design(scene, unlinked, tmp_path)
    assert "link" in str(out.measurements["error"])


def test_no_gpu_is_blenders_failure_not_the_models(
    tmp_path: Path, scene: SceneInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    with pytest.raises(BlenderError, match="no GPU"):
        run_design(scene, BOX, tmp_path)


def test_a_main_guarded_script_runs(tmp_path: Path, scene: SceneInput) -> None:
    body = "\n".join("    " + line for line in BOX.strip().splitlines())
    script = f"def main():\n{body}\n\nif __name__ == '__main__':\n    main()\n"
    out = run_design(scene, script, tmp_path)
    assert out.measurements["error"] is None
    assert out.measurements["faces_xy"]


def test_building_parts_besides_the_dwelling_are_rejected(
    tmp_path: Path, scene: SceneInput
) -> None:
    """Only the Dwelling is measured, so a separate roof or deck would go unchecked."""
    roof = "bpy.ops.mesh.primitive_cube_add(size=1, location=(2.0, 1.0, 5.0))\n"
    roof += "bpy.context.active_object.name = 'Roof'\n"
    out = run_design(scene, BOX + roof, tmp_path)
    error = str(out.measurements["error"])
    assert "Roof" in error and "Dwelling" in error
    assert out.glb is None and out.png is None


def test_lights_and_cameras_may_be_added(tmp_path: Path, scene: SceneInput) -> None:
    light = "bpy.ops.object.light_add(type='POINT', location=(0.0, 0.0, 8.0))\n"
    out = run_design(scene, BOX + light, tmp_path)
    assert out.measurements["error"] is None


def test_a_removed_parcel_boundary_is_restored(tmp_path: Path, scene: SceneInput) -> None:
    parcel = ((10.0, 10.0), (40.0, 10.0), (40.0, 30.0), (10.0, 30.0), (10.0, 10.0))
    framed = scene_input(_GRID, LocalFrame.centred_on(_GRID.bbox), [parcel])
    script = BOX + "bpy.data.objects.remove(bpy.data.objects['Parcel.0'])\n"
    out = run_design(framed, script, tmp_path)
    assert out.measurements["error"] is None
    assert out.glb is not None and b"Parcel.0" in out.glb.read_bytes()


@pytest.mark.parametrize("ending", ["import sys\nsys.exit(0)\n", "raise SystemExit(3)\n"])
def test_a_script_that_exits_gets_feedback(tmp_path: Path, scene: SceneInput, ending: str) -> None:
    out = run_design(scene, BOX + ending, tmp_path)
    assert "SystemExit" in str(out.measurements["error"])


@pytest.mark.parametrize(
    ("script", "timeout_s"),
    [("import os\nos.abort()\n", 120.0), ("import time\ntime.sleep(600)\n", 20.0)],
)
def test_a_script_that_crashes_or_hangs_blender_gets_feedback(
    tmp_path: Path, scene: SceneInput, script: str, timeout_s: float
) -> None:
    out = run_design(scene, script, tmp_path, timeout_s=timeout_s)
    assert "did not finish" in str(out.measurements["error"])
    assert out.glb is None and out.png is None


def test_the_script_cannot_reach_host_sockets(tmp_path: Path, scene: SceneInput) -> None:
    """Unix sockets under /run (the user's D-Bus, Docker) would escape the sandbox."""
    script = (
        "import os, socket\n"
        "s = socket.socket(socket.AF_UNIX)\n"
        "s.connect(f'/run/user/{os.getuid()}/bus')\n"
    )
    out = run_design(scene, script, tmp_path)
    assert "FileNotFoundError" in str(out.measurements["error"])


def test_the_script_cannot_write_the_hosts_disk(tmp_path: Path, scene: SceneInput) -> None:
    """Its inputs are mounted read-only and its scratch space is a tmpfs: links,
    FIFOs and files it leaves behind never reach the host."""
    plant = (
        "import atexit, os, sys\n"
        "here = os.path.dirname(sys.argv[sys.argv.index('--') + 1])\n"
        "for name in ('attempt.json', 'design.blend'):\n"
        "    try:\n"
        "        os.symlink('/etc/hostname', os.path.join(here, name))\n"
        "    except OSError:\n"
        "        pass\n"
        "scratch = sys.argv[-2]\n"
        "atexit.register(lambda: (os.remove(scratch + '/design.blend'),"
        " os.mkfifo(scratch + '/design.blend')))\n"
    )
    out = run_design(scene, BOX + plant, tmp_path)
    assert out.measurements["error"] is None
    assert not os.path.lexists(tmp_path / "attempt.json")
    blend = tmp_path / "script" / "design.blend"
    assert not blend.is_symlink() and blend.is_file()


def test_the_script_cannot_reach_host_shared_memory(tmp_path: Path, scene: SceneInput) -> None:
    name = f"button-nz-sandbox-{os.getpid()}"
    out = run_design(scene, BOX + f"open('/dev/shm/{name}', 'w').write('x')\n", tmp_path)
    assert out.measurements["error"] is None
    assert not Path("/dev/shm", name).exists()


def test_the_scratch_space_is_size_limited(tmp_path: Path, scene: SceneInput) -> None:
    fill = (
        "import sys\n"
        "with open(sys.argv[-2] + '/fill', 'wb') as f:\n"
        "    for _ in range(1200):\n"
        "        f.write(bytes(1 << 20))\n"
    )
    out = run_design(scene, BOX + fill, tmp_path)
    assert "No space left on device" in str(out.measurements["error"])


def test_the_script_has_a_memory_limit(tmp_path: Path, scene: SceneInput) -> None:
    out = run_design(scene, BOX + "hog = bytearray(20 << 30)\n", tmp_path)
    assert "MemoryError" in str(out.measurements["error"])


def test_a_flood_of_output_is_harmless(tmp_path: Path, scene: SceneInput) -> None:
    flood = "import sys\nfor _ in range(300):\n    sys.stdout.write('x' * (1 << 20))\n"
    out = run_design(scene, BOX + flood, tmp_path)
    assert out.measurements["error"] is None
