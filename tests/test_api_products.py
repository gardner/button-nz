"""Tests for the prefab products that fit an accepted design, over HTTP."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from button_nz.api.app import create_app
from button_nz.catalogue import Product
from button_nz.demo_site import load_demo_site
from test_api import ScriptedModel, Service
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
