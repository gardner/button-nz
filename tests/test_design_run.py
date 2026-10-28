"""Real sandboxed Blender runs of model-written design scripts.
Excluded by default; run with `pytest -m blender`."""

import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray
from shapely import Polygon

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
        "tiny = {'error': None, 'triangles': [[[0, 0, 0], [1, 0, 0], [1, 1, 1]]]}\n"
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
    assert out.measurements["triangles"]


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


EAVES = """
bpy.ops.mesh.primitive_cube_add(size=1, location=(2.0, 1.0, 3.75))
roof = bpy.context.active_object
roof.scale = (8.0, 7.0, 0.3)
bpy.ops.object.select_all(action='DESELECT')
roof.select_set(True)
dwelling.select_set(True)
bpy.context.view_layer.objects.active = dwelling
bpy.ops.object.join()
"""


def test_eaves_are_in_the_outline_but_not_the_wall_footprint(
    tmp_path: Path, scene: SceneInput
) -> None:
    out = run_design(scene, BOX + EAVES, tmp_path)
    measured = parse_measurements(out.measurements)
    assert measured.footprint is not None and measured.outline is not None
    assert Polygon(measured.footprint).area == pytest.approx(30.0)  # the 6 m x 5 m walls
    assert Polygon(measured.outline).area == pytest.approx(56.0)  # the 8 m x 7 m roof
    assert (measured.z_min, measured.z_max) == pytest.approx((0.0, 3.9))


def test_a_hidden_dwelling_is_still_rendered(tmp_path: Path, scene: SceneInput) -> None:
    """What is checked is what is shown: hiding the Dwelling from the render doesn't work."""
    shown = run_design(scene, BOX, tmp_path / "shown")
    hidden = run_design(scene, BOX + "dwelling.hide_render = True\n", tmp_path / "hidden")
    assert shown.png is not None and hidden.png is not None
    a, b = _pixels(shown.png), _pixels(hidden.png)
    assert np.abs(a - b).mean() < 2.0


def test_too_detailed_a_dwelling_is_feedback_without_a_render(
    tmp_path: Path, scene: SceneInput
) -> None:
    dense = (
        "bpy.ops.mesh.primitive_grid_add(x_subdivisions=400, y_subdivisions=400, size=6)\n"
        "bpy.context.active_object.name = 'Dwelling'\n"
    )
    out = run_design(scene, dense, tmp_path)
    assert "triangles" in str(out.measurements["error"])
    assert out.glb is None and out.png is None
    assert not (tmp_path / "design.glb").exists()


def test_the_script_sees_no_host_terminals(tmp_path: Path, scene: SceneInput) -> None:
    probe = "import os\nraise SystemExit(repr(sorted(os.listdir('/dev/pts'))))\n"
    out = run_design(scene, probe, tmp_path)
    assert "['ptmx']" in str(out.measurements["error"])


def _pixels(png: Path) -> NDArray[np.float64]:
    """A rendered PNG's pixels (GDAL reads PNG too)."""
    rio: Any = rasterio
    with rio.open(png) as image:
        return np.asarray(image.read(), dtype=np.float64)


def test_runaway_modifiers_hit_the_measuring_passs_memory_limit(
    tmp_path: Path, scene: SceneInput
) -> None:
    """A small mesh whose modifiers expand beyond memory is the model's feedback,
    not an exhausted host."""
    explode = "m = dwelling.modifiers.new('more', 'SUBSURF')\nm.levels = 11\nm.render_levels = 11\n"
    out = run_design(scene, BOX + explode, tmp_path, timeout_s=300)
    assert out.measurements["error"]
    assert out.glb is None and out.png is None


def test_a_forged_saved_frame_doesnt_replace_the_design(tmp_path: Path, scene: SceneInput) -> None:
    forge = "import os, sys\nos.write(int(sys.argv[-1]), b'B' + (4).to_bytes(8, 'big') + b'junk')\n"
    out = run_design(scene, BOX + forge, tmp_path)
    assert out.measurements["error"] is None  # the runner's own, later frame wins


def test_an_unreadable_design_file_is_the_models_feedback(
    tmp_path: Path, scene: SceneInput
) -> None:
    """Pass 1 stands in, sending junk as the design file; real Blender measures it."""
    real = shutil.which("blender")
    assert real is not None
    fake = tmp_path / "bin" / "blender"
    fake.parent.mkdir()
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "if any(a.endswith('design_script.py') for a in sys.argv):\n"
        "    fd = int(sys.argv[-1])\n"
        "    os.write(fd, b'S' + bytes(8))\n"
        "    os.write(fd, b'B' + (4).to_bytes(8, 'big') + b'junk')\n"
        "else:\n"
        f"    os.execv({real!r}, [{real!r}, *sys.argv[1:]])\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    out = run_design(scene, BOX, tmp_path / "run", blender=str(fake))
    assert "couldn't be read" in str(out.measurements["error"])


def test_modifiers_are_measured_as_they_render(tmp_path: Path, scene: SceneInput) -> None:
    """An Array hidden from the viewport still renders: it must be measured too."""
    copies = "m = dwelling.modifiers.new('copies', 'ARRAY')\nm.count = 3\nm.show_viewport = False\n"
    out = run_design(scene, BOX + copies, tmp_path)
    measured = parse_measurements(out.measurements)
    assert measured.outline is not None
    xs = [x for x, _ in measured.outline]
    assert max(xs) - min(xs) == pytest.approx(18.0)  # three 6 m boxes side by side


def test_the_script_sees_only_system_directories(tmp_path: Path, scene: SceneInput) -> None:
    probe = "import os\nraise SystemExit(repr(sorted(os.listdir('/'))))\n"
    out = run_design(scene, probe, tmp_path)
    listing = str(out.measurements["error"])
    for hidden in ("'srv'", "'var'", "'root'", "'mnt'", "'media'"):
        assert hidden not in listing


def test_a_fork_bomb_hits_the_task_limit(tmp_path: Path, scene: SceneInput) -> None:
    bomb = (
        "import os, time\n"
        "children = 0\n"
        "try:\n"
        "    for _ in range(5000):\n"
        "        if os.fork() == 0:\n"
        "            time.sleep(30)\n"
        "            os._exit(0)\n"
        "        children += 1\n"
        "except OSError as error:\n"
        "    raise SystemExit(f'stopped after {children}: {error}')\n"
    )
    out = run_design(scene, BOX + bomb, tmp_path, timeout_s=120)
    assert "stopped after" in str(out.measurements["error"])


def test_geometry_that_differs_in_the_render_is_feedback(tmp_path: Path, scene: SceneInput) -> None:
    """A node tree asking Is Viewport can build one thing to measure and another to render."""
    nodes = (
        "tree = bpy.data.node_groups.new('switch', 'GeometryNodeTree')\n"
        "tree.nodes.new('GeometryNodeIsViewport')\n"
        "dwelling.modifiers.new('nodes', 'NODES').node_group = tree\n"
    )
    out = run_design(scene, BOX + nodes, tmp_path)
    assert "Is Viewport" in str(out.measurements["error"])


def test_a_transparent_dwelling_is_still_rendered(tmp_path: Path, scene: SceneInput) -> None:
    """The render uses a trusted opaque material: what is checked is what is shown."""
    glass = (
        "mat = bpy.data.materials.new('invisible')\n"
        "mat.use_nodes = True\n"
        "nodes = mat.node_tree.nodes\n"
        "nodes.remove(nodes['Principled BSDF'])\n"
        "clear = nodes.new('ShaderNodeBsdfTransparent')\n"
        "mat.node_tree.links.new(clear.outputs[0], nodes['Material Output'].inputs[0])\n"
        "dwelling.data.materials.append(mat)\n"
    )
    shown = run_design(scene, BOX, tmp_path / "shown")
    hidden = run_design(scene, BOX + glass, tmp_path / "hidden")
    assert shown.png is not None and hidden.png is not None
    assert np.abs(_pixels(shown.png) - _pixels(hidden.png)).mean() < 2.0


def test_the_script_gets_no_gpu(tmp_path: Path, scene: SceneInput) -> None:
    probe = (
        "import glob\nraise SystemExit(repr(glob.glob('/dev/nvidia*') + glob.glob('/dev/dri')))\n"
    )
    out = run_design(scene, probe, tmp_path)
    assert "[]" in str(out.measurements["error"])


INSTANCES = """
tree = bpy.data.node_groups.new('copies', 'GeometryNodeTree')
tree.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
tree.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
inp, out = tree.nodes.new('NodeGroupInput'), tree.nodes.new('NodeGroupOutput')
line = tree.nodes.new('GeometryNodeMeshLine')
line.inputs['Count'].default_value = 3
line.inputs['Offset'].default_value = (12.0, 0.0, 0.0)
cube = tree.nodes.new('GeometryNodeMeshCube')
place = tree.nodes.new('GeometryNodeInstanceOnPoints')
join = tree.nodes.new('GeometryNodeJoinGeometry')
tree.links.new(line.outputs[0], place.inputs['Points'])
tree.links.new(cube.outputs[0], place.inputs['Instance'])
tree.links.new(inp.outputs[0], join.inputs[0])
tree.links.new(place.outputs[0], join.inputs[0])
tree.links.new(join.outputs[0], out.inputs[0])
dwelling.modifiers.new('copies', 'NODES').node_group = tree
"""


def test_geometry_nodes_instances_are_measured(tmp_path: Path, scene: SceneInput) -> None:
    """Unrealised instances render, so they must be measured too."""
    out = run_design(scene, BOX + INSTANCES, tmp_path)
    measured = parse_measurements(out.measurements)
    assert measured.outline is not None or measured.parts > 1
    triangles = out.measurements["triangles"]
    xs = [p[0] for tri in triangles for p in tri]
    assert max(xs) > 20.0  # the third cube, 24 m along x


def test_non_finite_geometry_is_feedback_not_a_crash(tmp_path: Path, scene: SceneInput) -> None:
    out = run_design(scene, BOX + "dwelling.data.vertices[0].co.x = float('nan')\n", tmp_path)
    assert "finite" in str(out.measurements["error"])
    assert out.glb is None and out.png is None
