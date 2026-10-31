"""Tests for placing a real product: a job names it, the worker designs to its
footprint, and its revisions keep it."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.store import Store
from button_nz.catalogue import Product
from button_nz.demo_site import load_demo_site
from test_api import ScriptedModel, fake_runner, synthetic_site


def product(
    id: str, length: float, width: float, labelled: bool = True, bounding_box: bool = False
) -> Product:
    return Product.parse(
        {
            "id": id,
            "supplier": "Test Homes",
            "model": id.title(),
            "url": "https://example.nz/cabin",
            "type": "transportable",
            "length_m": length,
            "width_m": width,
            "dimensions_labelled": labelled,
            "bounding_box": bounding_box,
            "floor_area_m2": round(length * width * 0.9, 1),
            "area_basis": "not stated",
            "bedrooms": 1,
            "bathrooms": 1,
            "price_nzd": None,
            "price_basis": "not published",
            "excludes": "site works",
            "west_coast": "not stated",
            "sources": ["https://example.nz/cabin"],
        }
    )


# fake_runner's "good" design has 6 m x 5 m walls.
CATALOGUE = (
    product("cabin", 6.0, 5.0),
    product("long", 8.0, 4.0),
    product("vague", 6, 5, labelled=False),
    product("stepped", 6, 5, bounding_box=True),
)


class Placing:
    def __init__(
        self, tmp_path: Path, *replies: str, catalogue: tuple[Product, ...] = CATALOGUE
    ) -> None:
        self.model = ScriptedModel(*replies)
        self.store = Store(tmp_path / "button.db")
        self.worker = Worker(
            self.store,
            site=synthetic_site,
            model=lambda: self.model,
            runs_dir=tmp_path / "runs",
            runner=fake_runner,
        )
        app = create_app(self.store, self.worker, load_demo_site(), products=catalogue)
        self.client = TestClient(app)

    def place(self, product_id: str) -> Any:
        return self.client.post("/designs", json={"brief": "A studio.", "product_id": product_id})


def test_a_placed_product_is_designed_to_and_checked(tmp_path: Path) -> None:
    placing = Placing(tmp_path, "good")
    created = placing.place("cabin")
    assert created.status_code == 202
    job_id = created.json()["id"]
    assert created.json()["product"] == {
        "id": "cabin",
        "name": "Test Homes Cabin",
        "length_m": 6.0,
        "width_m": 5.0,
    }
    assert placing.worker.run_next()
    brief = placing.model.seen[0][1].text
    assert "Test Homes Cabin" in brief and "6 × 5 m" in brief
    job = placing.client.get(f"/designs/{job_id}").json()
    assert job["accepted_attempt"] == 1
    assert "product_footprint: pass" in job["attempts"][0]["feedback"]


def test_walls_that_are_not_the_product_are_not_accepted(tmp_path: Path) -> None:
    placing = Placing(tmp_path, "good", "good", "good")
    job_id = placing.place("long").json()["id"]
    assert placing.worker.run_next()
    job = placing.client.get(f"/designs/{job_id}").json()
    assert job["accepted_attempt"] is None
    assert "product_footprint: fail" in job["attempts"][0]["feedback"]


@pytest.mark.parametrize("product_id", ["nope", "vague", "stepped"])
def test_only_a_product_whose_footprint_is_a_known_rectangle_can_be_placed(
    tmp_path: Path, product_id: str
) -> None:
    refused = Placing(tmp_path).place(product_id)
    assert refused.status_code == 422
    assert product_id in refused.json()["detail"]


def test_a_design_without_a_product_has_none(tmp_path: Path) -> None:
    created = Placing(tmp_path).client.post("/designs", json={"brief": "A studio."})
    assert created.json()["product"] is None


def test_a_revision_keeps_the_product_it_places(tmp_path: Path) -> None:
    placing = Placing(tmp_path, "good", "good")
    parent = placing.place("cabin").json()["id"]
    assert placing.worker.run_next()
    revised = placing.client.post(
        f"/designs/{parent}/revisions", json={"instruction": "Turn it to face north."}
    )
    assert revised.json()["product"]["id"] == "cabin"
    assert placing.worker.run_next()
    assert "6 × 5 m" in placing.model.seen[1][1].text
    job = placing.client.get(f"/designs/{revised.json()['id']}").json()
    assert "product_footprint: pass" in job["attempts"][0]["feedback"]


def test_a_design_keeps_its_product_as_it_was_when_placed(tmp_path: Path) -> None:
    job_id = Placing(tmp_path).place("cabin").json()["id"]
    resized = (product("cabin", 8.0, 4.0),)  # a later catalogue changes the product
    placing = Placing(tmp_path, "good", catalogue=resized)
    assert placing.client.get(f"/designs/{job_id}").json()["product"]["length_m"] == 6.0
    assert placing.worker.run_next()
    job = placing.client.get(f"/designs/{job_id}").json()
    assert "product_footprint: pass" in job["attempts"][0]["feedback"]  # checked as placed
