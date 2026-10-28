"""Tests for button_nz.geo.tiles, LINZ Topo50 tile names to NZTM bounds."""

import pytest

from button_nz.geo.tiles import tile_bounds


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
