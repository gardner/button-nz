"""Tests for button_nz.agent.sections: plan outlines and horizontal sections of
a triangle mesh."""

import pytest
from shapely import Polygon

from button_nz.agent.sections import outline, outline_above, section
from meshes import box


def test_the_outline_is_everything_seen_from_above() -> None:
    walls = box(0, 0, 0, 8, 8, 3)
    eaves = box(-1, -1, 3, 9, 9, 3.3)
    shape = outline(walls + eaves)
    assert isinstance(shape, Polygon)
    assert shape.area == pytest.approx(100.0)


def test_a_section_cuts_the_walls_not_the_eaves() -> None:
    walls = box(0, 0, 0, 8, 8, 3)
    eaves = box(-1, -1, 3, 9, 9, 3.3)
    cut = section(walls + eaves, 1.0)
    assert cut.area == pytest.approx(64.0)
    assert cut.bounds == pytest.approx((0, 0, 8, 8))


def test_a_section_through_shared_vertices_is_closed_and_counted_once() -> None:
    """Two boxes stacked at z = 1: the cut passes exactly through their shared face."""
    stacked = box(0, 0, 0, 4, 2, 1) + box(0, 0, 1, 4, 2, 2)
    assert section(stacked, 1.0).area == pytest.approx(8.0)


def test_an_open_mesh_has_no_closed_section() -> None:
    sheet = [[[0.0, 0.0, 0.0], [4.0, 0.0, 2.0], [4.0, 4.0, 2.0]]]
    assert section(sheet, 1.0).is_empty


def test_two_boxes_side_by_side_give_two_parts() -> None:
    cut = section(box(0, 0, 0, 2, 2, 2) + box(5, 0, 0, 7, 2, 2), 1.0)
    assert cut.area == pytest.approx(8.0)
    assert len(getattr(cut, "geoms", [cut])) == 2


def test_the_outline_above_a_height_clips_triangles_that_cross_it() -> None:
    """A triangle from z 0 to 2 contributes only its part above z 1."""
    slope = [[[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [0.0, 0.0, 2.0]]]  # vertical: no area above
    tilted = [[[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [0.0, 4.0, 2.0]]]
    assert outline_above(slope, 1.0).area == pytest.approx(0.0)
    assert outline_above(tilted, 1.0).area == pytest.approx(2.0)  # the top quarter of 8 m²


def test_vertical_faces_stay_in_the_outline() -> None:
    """A screen wall seen from above is a line: it still reaches as far as it goes."""
    screen = [[[8.0, 3.0, 0.0], [14.0, 3.0, 0.0], [14.0, 3.0, 2.0]]]
    shape = outline(box(0, 0, 0, 8, 6, 3) + screen)
    assert shape.bounds[2] == pytest.approx(14.0, abs=0.01)
    assert shape.area == pytest.approx(48.0, abs=0.1)
