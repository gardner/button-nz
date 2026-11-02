"""The Dwelling's silhouette from the render camera, rendered by the trusted pass.
Real sandboxed Blender runs; excluded by default, run with `pytest -m blender`."""

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from button_nz.blender_worker.run import DesignOutputs, run_design
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender

_BOX = """
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, {y}, 1.8))
dwelling = bpy.context.active_object
dwelling.name = "Dwelling"
dwelling.scale = (6.0, 5.0, 3.6)
"""
IN_VIEW = _BOX.format(x=2.0, y=1.0)
OUT_OF_VIEW = _BOX.format(x=2.0, y=-200.0)  # far behind the camera, which looks north
_DEM = np.full((40, 50), 10.0)


def _scene(ndsm: NDArray[np.float64]) -> SceneInput:
    grid = TerrainGrid((0.0, 0.0, 50.0, 40.0), 1.0, _DEM, ndsm, ("synthetic",))
    return scene_input(grid, LocalFrame.centred_on(grid.bbox), [])


def _open(tmp_path: Path, script: str, ndsm: NDArray[np.float64] | None = None) -> DesignOutputs:
    scene = _scene(np.zeros_like(_DEM) if ndsm is None else ndsm)
    return run_design(scene, script, tmp_path)


def _mask(out: DesignOutputs) -> NDArray[np.bool_]:
    assert out.mask is not None
    return _white(out, out.mask)


def _outline(out: DesignOutputs) -> NDArray[np.bool_]:
    assert out.outline is not None
    return _white(out, out.outline)


def _white(out: DesignOutputs, png: Path) -> NDArray[np.bool_]:
    assert out.png is not None
    with Image.open(png) as mask, Image.open(out.png) as render:
        assert mask.size == render.size  # same camera, same resolution
        values = np.asarray(mask.convert("L"))
    assert set(np.unique(values)) <= {0, 255}  # white is the Dwelling, black the rest
    return values == 255


def _rgb(png: Path) -> NDArray[np.int16]:
    with Image.open(png) as image:
        return np.asarray(image.convert("RGB"), dtype=np.int16)


def test_the_mask_covers_the_dwelling_where_the_render_shows_it(tmp_path: Path) -> None:
    shown = _open(tmp_path / "shown", IN_VIEW)
    absent = _open(tmp_path / "absent", OUT_OF_VIEW)
    mask = _mask(shown)
    assert mask.sum() > 500
    assert shown.png is not None and absent.png is not None
    # Where the two renders differ is the Dwelling and its shadow: the mask is in there.
    changed = np.abs(_rgb(shown.png) - _rgb(absent.png)).max(axis=2) > 12
    assert changed[mask].mean() > 0.95


def test_a_dwelling_out_of_view_has_an_empty_mask(tmp_path: Path) -> None:
    assert not _mask(_open(tmp_path, OUT_OF_VIEW)).any()


def test_what_stands_in_front_of_the_dwelling_hides_it(tmp_path: Path) -> None:
    """Occlusion, not visibility: a 20 m wall between the camera and the Dwelling
    leaves nothing of it in the mask, though it is inside the frame."""
    ndsm = np.zeros_like(_DEM)
    ndsm[27:29, 5:45] = 20.0  # 8 m south of the Dwelling, across its whole width
    assert _mask(_open(tmp_path / "open", IN_VIEW)).any()
    assert not _mask(_open(tmp_path / "walled", IN_VIEW, ndsm)).any()


def test_a_partly_hidden_dwelling_shows_only_its_visible_part(tmp_path: Path) -> None:
    low = np.zeros_like(_DEM)
    low[27:29, 5:45] = 9.0  # hides its south wall from the camera, not its roof
    whole = _mask(_open(tmp_path / "whole", IN_VIEW)).sum()
    part = _mask(_open(tmp_path / "part", IN_VIEW, low)).sum()
    assert 0 < part < 0.8 * whole


def test_the_outline_is_the_whole_dwelling_whatever_stands_in_front(tmp_path: Path) -> None:
    """Muse Image redraws what stands in front, and may draw it lower so the whole
    house shows: the check needs the outline nothing hides too (#133)."""
    low = np.zeros_like(_DEM)
    low[27:29, 5:45] = 9.0  # hides its south wall from the camera, not its roof
    whole = _open(tmp_path / "whole", IN_VIEW)
    part = _open(tmp_path / "part", IN_VIEW, low)
    assert np.array_equal(_outline(whole), _mask(whole))  # nothing hides it
    assert np.array_equal(_outline(part), _mask(whole))
    assert not (_mask(part) & ~_outline(part)).any()  # what shows is part of it


def test_a_dwelling_out_of_view_has_an_empty_outline(tmp_path: Path) -> None:
    assert not _outline(_open(tmp_path, OUT_OF_VIEW)).any()
