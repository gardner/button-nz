"""Tests for button_nz.agent.sections: plan outlines and horizontal sections of
a triangle mesh."""

import pytest
from shapely import Polygon

from button_nz.agent.sections import outline, section
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
