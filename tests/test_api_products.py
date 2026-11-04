"""Tests for the prefab products that fit an accepted design, over HTTP."""

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from numpy.typing import NDArray

import button_nz.api.products as products_module
from button_nz.agent.site import DesignSite
from button_nz.api.app import create_app
from button_nz.api.store import Job
from button_nz.catalogue import Product
from button_nz.demo_site import load_demo_site
from button_nz.geo.terrain import TerrainGrid
from test_api import ScriptedModel, Service, synthetic_site
from test_catalogue import product

# The scripted "good" design's walls are 6 m x 5 m.
FITS = product(id="fits", length_m=5.9, width_m=4.9, floor_area_m2=26)
TOO_LONG = product(id="too-long", length_m=9.0, width_m=3.5, floor_area_m2=31)
UNLABELLED = product(id="unlabelled", length_m=5.0, width_m=4.0, dimensions_labelled=False)


def with_products(tmp_path: Path, *products: dict[str, Any], **kwargs: Any) -> Service:
    service = Service(tmp_path, **kwargs)
    catalogue = tuple(Product.parse(p) for p in products)
    app = create_app(service.store, service.worker, load_demo_site(), products=catalogue)
    service.client = TestClient(app)
    return service


def test_the_products_that_fit_an_accepted_design(tmp_path: Path) -> None:
    service = with_products(tmp_path, TOO_LONG, FITS, UNLABELLED)
    job_id = service.queue()
    service.worker.run_next()  # attempt 1 fails, attempt 2 is accepted
    found = service.client.get(f"/designs/{job_id}/products").json()
    assert [p["id"] for p in found["fits"]] == ["fits"]
    assert [p["id"] for p in found["unchecked"]] == ["unlabelled"]
    assert found["footprint_m2"] == 30.0
    assert found["fits"][0]["sources"] == ["https://example.com/sample"]
    assert "height" in found["basis"] and "eaves" in found["basis"]  # what isn't checked


def test_only_an_accepted_design_has_products(tmp_path: Path) -> None:
    service = with_products(tmp_path, FITS, model=lambda: ScriptedModel("near", "near", "near"))
    job_id = service.queue()
    assert service.client.get(f"/designs/{job_id}/products").status_code == 409
    service.worker.run_next()  # nothing accepted
    assert service.client.get(f"/designs/{job_id}/products").status_code == 409
    assert service.client.get("/designs/nope/products").status_code == 404


def test_the_real_catalogue_is_served_by_default(tmp_path: Path) -> None:
    service = Service(tmp_path)
    job_id = service.queue()
    service.worker.run_next()
    found = service.client.get(f"/designs/{job_id}/products").json()
    assert found["fits"] == []  # nothing real is as small as 6 m x 5 m
    assert {p["supplier"] for p in found["unchecked"]} == {"Keith Hay Homes"}


def test_the_walls_are_measured_once_per_accepted_attempt(tmp_path: Path) -> None:
    service = with_products(tmp_path, FITS)
    job_id = service.queue()
    service.worker.run_next()
    first = service.client.get(f"/designs/{job_id}/products").json()
    (tmp_path / "runs" / job_id / "attempt-2" / "measurements.json").unlink()
    assert service.client.get(f"/designs/{job_id}/products").json() == first


def test_the_whole_catalogue_can_be_browsed_before_any_design(tmp_path: Path) -> None:
    service = with_products(tmp_path, TOO_LONG, FITS, UNLABELLED)
    listed = service.client.get("/products").json()
    assert [p["id"] for p in listed] == ["too-long", "fits", "unlabelled"]  # as catalogued
    assert listed[1]["length_m"] == 5.9 and "price_nzd" in listed[1]


def test_a_product_the_search_cant_stand_within_floor_level_stays_listed_with_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = with_products(tmp_path, FITS)
    job_id = service.queue()
    service.worker.run_next()  # designed on flat ground
    monkeypatch.setattr(service.worker, "decided_site", steep)  # now steep
    catalogue = (Product.parse(FITS),)
    app = create_app(service.store, service.worker, load_demo_site(), products=catalogue)
    found = TestClient(app).get(f"/designs/{job_id}/products").json()
    (listed,) = found["fits"]  # a sampled search proves nothing: never dropped
    note = listed["floor_level_note"]
    assert "earthworks" in note
    assert re.search(r"inside the design's walls the ground under it varies by \d+\.\d\d m", note)
    assert re.search(r"at every position the search tried .* by at least \d+\.\d\d m", note)
    assert "floor level" in found["basis"]
    assert "unplaceable" not in found


def test_a_product_that_can_stand_on_the_site_still_fits(tmp_path: Path) -> None:
    service = with_products(tmp_path, FITS)  # the flat synthetic site
    job_id = service.queue()
    service.worker.run_next()
    found = service.client.get(f"/designs/{job_id}/products").json()
    assert [p["id"] for p in found["fits"]] == ["fits"]
    assert found["fits"][0]["floor_level_note"] is None


def steep(_: Job | None = None) -> DesignSite:
    """The synthetic site with its ground rising 0.4 m per m eastwards."""
    site = synthetic_site()
    grid = site.context.terrain
    _, cols = grid.dem.shape
    dem: NDArray[np.float64] = grid.dem + 0.4 * np.arange(cols, dtype=np.float64)
    steeper = TerrainGrid(grid.bbox, grid.cell_m, dem, grid.ndsm, grid.sources)
    return replace(site, context=replace(site.context, terrain=steeper))


def test_a_product_that_stands_where_the_design_does_has_no_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = with_products(tmp_path, FITS)  # flat: it stands inside the design's walls
    job_id = service.queue()
    service.worker.run_next()
    # a search that missed every flat pose: the walls' own pose still counts
    monkeypatch.setattr(products_module, "least_ground_range", missed)
    found = service.client.get(f"/designs/{job_id}/products").json()
    assert [p["id"] for p in found["fits"]] == ["fits"]
    assert found["fits"][0]["floor_level_note"] is None


def missed(*_: Any, **__: Any) -> float:
    return 1.5
