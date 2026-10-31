"""Tests for the town screen's geometry: where on a section a flat may stand
under Schedule 1A's siting rules, and which real products fit there."""

from typing import Any

import numpy as np
import pytest
from shapely import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry

from button_nz.catalogue import Product
from button_nz.geo.terrain import TerrainGrid
from button_nz.town.lidar import tall_cells
from button_nz.town.screen import (
    EAVE_ALLOWANCE_M,
    fitting,
    room,
    screen_section,
)
from test_catalogue import product


def prefab(id: str, length: float, width: float, **overrides: Any) -> Product:
    return Product.parse(
        product(id=id, length_m=length, width_m=width, floor_area_m2=min(length * width - 1, 70))
        | overrides
    )


def grid(ndsm: list[list[float]], left: float = 0.0, top: float = 10.0) -> TerrainGrid:
    cells = np.array(ndsm, dtype=np.float64)
    rows, cols = cells.shape
    return TerrainGrid((left, top - rows, left + cols, top), 1.0, np.zeros_like(cells), cells, ())


# --- room -------------------------------------------------------------------


def test_room_is_two_metres_inside_the_boundary() -> None:
    inside = room(box(0, 0, 20, 30), [])
    assert inside.within(box(2, 2, 18, 28))
    assert inside.area == pytest.approx(16 * 26, rel=1e-3)


def test_room_keeps_two_metres_from_a_reflex_corner_of_the_boundary() -> None:
    ell = Polygon([(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)])
    assert room(ell, []).distance(ell.exterior) >= 2.0 - 1e-9


def test_room_keeps_two_metres_from_every_building() -> None:
    shed = box(8, 8, 12, 12)
    left = room(box(0, 0, 20, 20), [shed])
    assert 2.0 - 1e-9 <= left.distance(shed) < 2.01  # never closer: the circle is circumscribed


def test_a_section_too_narrow_has_no_room() -> None:
    assert room(box(0, 0, 4, 30), []).is_empty


# --- fitting ----------------------------------------------------------------


def test_fitting_names_the_products_that_fit_some_part_of_the_room() -> None:
    products = [prefab("small", 12, 5), prefab("long", 20, 5), prefab("wide", 9, 9)]
    split = MultiPolygon([box(0, 0, 13, 6), box(30, 0, 40, 10)])
    assert fitting(split, products) == ("wide", "small")  # largest first


def test_unlabelled_dimensions_never_fit() -> None:
    unlabelled = prefab("unknown", 5, 4, dimensions_labelled=False)
    assert fitting(box(0, 0, 50, 50), [unlabelled]) == ()


def test_the_eave_allowance_grows_the_outline_on_every_side() -> None:
    snug = prefab("snug", 15.5, 25.5)
    assert fitting(box(0, 0, 16, 26), [snug]) == ("snug",)
    assert fitting(box(0, 0, 16, 26), [snug], EAVE_ALLOWANCE_M) == ()
    assert fitting(box(0, 0, 16.7, 26.7), [snug], EAVE_ALLOWANCE_M) == ("snug",)


def test_an_empty_room_fits_nothing() -> None:
    assert fitting(Polygon(), [prefab("small", 2, 2)]) == ()


# --- the LiDAR --------------------------------------------------------------


def test_tall_cells_are_the_cells_over_two_metres_in_nztm() -> None:
    terrain = grid([[0, 0, 0], [0, 2.5, 0], [0, 0, 1.9]], left=100, top=203)
    tall = tall_cells(terrain, (100, 200, 103, 203))
    assert tall.equals(box(101, 201, 102, 202))


def test_tall_cells_outside_the_bounds_are_left_out() -> None:
    terrain = grid([[3, 0, 0, 0], [0, 0, 0, 3]], left=0, top=2)
    assert tall_cells(terrain, (2, 0, 4, 2)).equals(box(3, 0, 4, 1))


def test_bounds_outside_the_grid_are_refused() -> None:
    with pytest.raises(ValueError, match="outside"):
        tall_cells(grid([[0]], left=0, top=1), (-5, 0, 1, 1))


# --- a section --------------------------------------------------------------


def test_a_section_is_screened_against_the_outlines_and_the_lidar() -> None:
    products = [prefab("small", 6, 4), prefab("large", 12, 6)]
    section = box(0, 0, 16, 10)  # room 12 x 6
    tree: BaseGeometry = box(13, 4, 14, 5)  # within 2 m of where "large" must stand
    result = screen_section(7, section, [], tree, products)
    assert result.parcel_id == 7
    assert result.area_m2 == pytest.approx(160)
    assert result.buildings == 0
    assert result.room_m2 == pytest.approx(72, rel=1e-2)
    assert result.fits == ("large", "small")
    assert result.fits_eaves == ("small",)
    assert result.clear == ("small",)
    assert result.clear_room_m2 < result.room_m2


def test_a_sliver_of_a_neighbours_outline_is_not_a_building_on_the_section() -> None:
    neighbours = box(19.95, 5, 30, 15)  # over the boundary by 5 cm: 0.5 m² on this section
    result = screen_section(1, box(0, 0, 20, 20), [neighbours], Polygon(), [prefab("s", 6, 4)])
    assert result.buildings == 0


def test_buildings_on_the_section_are_counted() -> None:
    house = box(1, 1, 5, 5)
    result = screen_section(1, box(0, 0, 40, 40), [house], Polygon(), [prefab("small", 6, 4)])
    assert result.buildings == 1
    assert result.clear == result.fits == ("small",)
