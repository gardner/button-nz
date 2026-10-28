"""Tests for button_nz.geo.tiles, LINZ Topo50 tile names to NZTM bounds."""

import pytest

from button_nz.geo.tiles import tile_bounds, tiles_covering


@pytest.mark.parametrize(
    ("name", "bounds"),
    [
        ("BS21_10000_0503", (1501600.0, 5334000.0, 1506400.0, 5341200.0)),
        ("BS21_1000_4730", (1505920.0, 5336160.0, 1506400.0, 5336880.0)),
        ("BS21_5000_1006", (1504000.0, 5334000.0, 1506400.0, 5337600.0)),
        ("BS21_1000_4830", (1505920.0, 5335440.0, 1506400.0, 5336160.0)),
    ],
)
def test_tile_bounds_match_the_linz_grid(name: str, bounds: tuple[float, ...]) -> None:
    assert tile_bounds(name) == bounds


@pytest.mark.parametrize(
    "name", ["BI21_1000_0101", "BS21_1234_0101", "BS21_1000_5101", "BS21_1000_0100", "nope"]
)
def test_invalid_tile_names_raise(name: str) -> None:
    with pytest.raises(ValueError, match="tile"):
        tile_bounds(name)


@pytest.mark.parametrize("name", ["BS21_1000_4730", "BS21_5000_1006", "BS21_10000_0503"])
def test_a_tile_covers_its_own_bounds(name: str) -> None:
    west, south, east, north = tile_bounds(name)
    inner = (west + 1, south + 1, east - 1, north - 1)
    scale = int(name.split("_")[1])
    assert tiles_covering(inner, scale) == [name]


def test_a_bbox_across_a_tile_edge_needs_both_tiles() -> None:
    west, south, _, north = tile_bounds("BS21_1000_4730")
    across = (west - 14.0, south + 600.0, west + 50.0, north - 20.0)
    assert tiles_covering(across, 1000) == ["BS21_1000_4729", "BS21_1000_4730"]


def test_a_tile_corner_needs_four_tiles_listed_north_west_first() -> None:
    _, south, east, _ = tile_bounds("BS21_1000_4730")
    corner = (east - 10.0, south - 10.0, east + 10.0, south + 10.0)
    assert tiles_covering(corner, 1000) == [
        "BS21_1000_4730",
        "BS21_1000_4731",
        "BS21_1000_4830",
        "BS21_1000_4831",
    ]


def test_a_bbox_ending_on_a_tile_edge_stays_in_its_tile() -> None:
    assert tiles_covering(tile_bounds("BS21_1000_4730"), 1000) == ["BS21_1000_4730"]
