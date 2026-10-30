"""Tests for the prefab catalogue: its sourced products, and which of them fit
inside an accepted design's footprint."""

import json
from pathlib import Path
from typing import Any

import pytest
from shapely import Polygon
from shapely.affinity import rotate, translate

from button_nz.catalogue import (
    CATALOGUE,
    CatalogueError,
    Product,
    fits,
    load_products,
    matches,
)


def product(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "sample-home",
        "supplier": "Sample Homes",
        "model": "Sample",
        "url": "https://example.com/sample",
        "type": "transportable",
        "length_m": 12.0,
        "width_m": 4.0,
        "dimensions_labelled": True,
        "floor_area_m2": 48.0,
        "area_basis": "not stated",
        "bedrooms": 2,
        "bathrooms": 1,
        "price_nzd": 190000,
        "price_basis": "incl GST, building only",
        "excludes": "delivery, foundations",
        "west_coast": "not stated",
        "sources": ["https://example.com/sample"],
    }
    return fields | overrides


def write(path: Path, *products: dict[str, Any]) -> Path:
    path.write_text(json.dumps({"researched": "2026-10-30", "products": products}), "utf-8")
    return path


def box(length: float, width: float, angle: float = 0.0, at: tuple[float, float] = (0, 0)):
    shape = Polygon([(0, 0), (length, 0), (length, width), (0, width)])
    return translate(rotate(shape, angle, origin=(0, 0)), *at)


# --- the catalogue ---------------------------------------------------------


def test_the_catalogue_is_sourced_and_within_the_exemption() -> None:
    products = load_products(CATALOGUE)
    assert len(products) >= 15
    assert len({p.id for p in products}) == len(products)
    for p in products:
        assert p.floor_area_m2 <= 70, p.id
        assert p.sources and all(s.startswith("https://") for s in p.sources), p.id
        assert p.url.startswith("https://"), p.id


def test_a_published_price_is_never_invented() -> None:
    by_id = {p.id: p for p in load_products(CATALOGUE)}
    assert by_id["living-little-oldham"].price_nzd == 180200
    assert by_id["south-peak-sefton"].price_nzd is None  # price on application


def test_unlabelled_dimensions_are_marked() -> None:
    by_id = {p.id: p for p in load_products(CATALOGUE)}
    assert not by_id["keith-hay-haven-70"].dimensions_labelled
    assert by_id["russley-kurow"].dimensions_labelled


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"sources": []}, "source"),
        ({"length_m": 0}, "length_m"),
        ({"width_m": -1}, "width_m"),
        ({"floor_area_m2": 75}, "70"),
        ({"url": "http://example.com"}, "https"),
        ({"price_nzd": 0}, "price"),
        # an internal area can't fill the whole outside footprint: the walls take some
        ({"area_basis": "internal", "floor_area_m2": 48.0}, "internal"),
    ],
)
def test_a_product_that_breaks_a_rule_is_refused(
    tmp_path: Path, override: dict[str, Any], problem: str
) -> None:
    with pytest.raises(CatalogueError, match=problem):
        load_products(write(tmp_path / "c.json", product(**override)))


def test_repeated_ids_are_refused(tmp_path: Path) -> None:
    with pytest.raises(CatalogueError, match="sample-home"):
        load_products(write(tmp_path / "c.json", product(), product()))


def test_a_missing_field_is_refused(tmp_path: Path) -> None:
    fields = product()
    del fields["price_basis"]
    with pytest.raises(CatalogueError, match="price_basis"):
        load_products(write(tmp_path / "c.json", fields))


# --- fitting ---------------------------------------------------------------


def test_a_product_fits_a_footprint_at_any_rotation_and_position() -> None:
    footprint = box(15, 5, angle=33, at=(1505940, 5336790))
    assert fits(footprint, 14.4, 4.2)
    assert fits(footprint, 4.2, 14.4)  # either way round
    assert not fits(footprint, 16.6, 4.2)
    assert not fits(footprint, 14.4, 5.4)


def test_an_exact_fit_fits() -> None:
    assert fits(box(9.6, 7.2, angle=-12), 9.6, 7.2)


def test_an_l_shaped_footprint_only_fits_what_its_arms_hold() -> None:
    corner = Polygon([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)])
    assert fits(corner, 9.9, 3.9)  # along one arm
    assert not fits(corner, 6, 6)  # its convex hull would take this


def test_matches_are_the_fitting_products_largest_first() -> None:
    products = [
        Product.parse(product(id="small", length_m=9, width_m=3.5, floor_area_m2=31)),
        Product.parse(product(id="large", length_m=14.4, width_m=4.2, floor_area_m2=60)),
        Product.parse(product(id="too-long", length_m=16.6, width_m=4.2, floor_area_m2=70)),
    ]
    found = matches(box(15, 5, angle=10), products)
    assert [p.id for p in found.fits] == ["large", "small"]
    assert found.unchecked == ()


def test_unlabelled_dimensions_are_never_presented_as_fitting() -> None:
    unlabelled = Product.parse(product(id="unlabelled", dimensions_labelled=False))
    found = matches(box(15, 5), [unlabelled])
    assert found.fits == ()
    assert [p.id for p in found.unchecked] == ["unlabelled"]


@pytest.mark.parametrize(
    "override", [{"length_m": "12"}, {"dimensions_labelled": 1}, {"bedrooms": 2.5}, {"extra": 1}]
)
def test_a_field_of_the_wrong_type_is_refused(tmp_path: Path, override: dict[str, Any]) -> None:
    with pytest.raises(CatalogueError, match="sample-home"):
        load_products(write(tmp_path / "c.json", product(**override)))
