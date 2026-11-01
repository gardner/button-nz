"""Tests for any-address sites over HTTP (button_nz.api.sites): search, build,
serve, survey and map, with LINZ and LiDAR faked (test_sites_build)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from httpx2 import Response  # what TestClient returns
from shapely import Point
from shapely.geometry import shape

from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.limits import DailyCap
from button_nz.api.sites import Sites, SiteService
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site
from button_nz.sites.registry import DEMO_ADDRESS_ID, DEMO_SITE_ID, SiteBuilder, SiteStore
from test_api import fake_runner, scripted, synthetic_site
from test_api_features import write_survey
from test_sites_build import sources


class Server:
    def __init__(self, tmp_path: Path, lidar: bool = True, cap: int | None = None) -> None:
        self.store = Store(tmp_path / "button.db")
        self.sites_store = SiteStore(tmp_path / "button.db")
        found = sources(lidar=lidar)
        self.builder = SiteBuilder(self.sites_store, tmp_path / "sites", lambda: found)
        demo_survey = tmp_path / "survey.geojson"
        write_survey(demo_survey, "shed", "tree")
        sites = Sites(
            self.sites_store,
            tmp_path / "sites",
            load_demo_site(),
            demo_survey,
            None,
            "the owner",
            lambda bbox: {"type": "FeatureCollection", "features": []},
        )
        daily = (
            None if cap is None else DailyCap(self.sites_store.created_since, cap, "site builds")
        )
        service = SiteService(sites, self.builder, found.addresses, daily)
        worker = Worker(self.store, synthetic_site, scripted, tmp_path / "runs", fake_runner)
        self.client = TestClient(create_app(self.store, worker, load_demo_site(), sites=service))

    def build(self, address_id: int = 7) -> dict[str, Any]:
        created = self.client.post("/sites", json={"address_id": address_id})
        assert created.status_code == 202, created.text
        self.builder.run_next()
        return self.client.get(f"/sites/{created.json()['id']}").json()


def test_addresses_are_searched_and_bad_queries_refused(tmp_path: Path) -> None:
    server = Server(tmp_path)
    found = server.client.get("/addresses", params={"q": "1 Test Street"}).json()
    assert found["addresses"][0]["id"] == 7  # the fake layer's one address
    assert server.client.get("/addresses", params={"q": "1=1; --"}).status_code == 422


def test_a_site_is_built_then_served_ready(tmp_path: Path) -> None:
    server = Server(tmp_path)
    created = server.client.post("/sites", json={"address_id": 7}).json()
    assert created == {
        "id": "1-test-street-reefton",
        "address": "1 Test Street, Reefton",
        "status": "building",
        "step": None,
        "error": None,
    }
    server.builder.run_next()
    site = server.client.get("/sites/1-test-street-reefton").json()
    assert site["status"] == "ready" and site["valuation_number"] is None
    west, south, east, north = site["bounds"]
    assert 171 < west < east < 172 and -43 < south < north < -42
    assert site["aerial"]["url"] == "/sites/1-test-street-reefton/aerial.png"
    assert all("asset" not in s and s["licence"] for s in site["sources"].values())
    png = server.client.get("/sites/1-test-street-reefton/aerial.png")
    assert png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"


def test_asking_again_for_an_address_returns_the_same_site(tmp_path: Path) -> None:
    server = Server(tmp_path)
    first = server.build()
    again = server.client.post("/sites", json={"address_id": 7}).json()
    assert again["id"] == first["id"] and again["status"] == "ready"


def test_the_demo_address_is_the_demo_site(tmp_path: Path) -> None:
    server = Server(tmp_path)
    demo = server.client.post("/sites", json={"address_id": DEMO_ADDRESS_ID}).json()
    assert demo["id"] == DEMO_SITE_ID and demo["status"] == "ready"
    assert demo["name"] == "35 Victory Street, Reefton"
    features = server.client.get(f"/sites/{DEMO_SITE_ID}/features").json()
    assert features["fixed"] is True and features["decided_by"] == "the owner"


def test_a_site_without_lidar_says_so(tmp_path: Path) -> None:
    site = Server(tmp_path, lidar=False).build()
    assert site["status"] == "no_lidar"
    assert "no LINZ 1 m LiDAR" in site["error"]


def test_a_built_sites_survey_is_open_to_its_visitor(tmp_path: Path) -> None:
    server = Server(tmp_path)
    site_id = server.build()["id"]
    features = server.client.get(f"/sites/{site_id}/features").json()
    assert features["fixed"] is False and features["features"] == []
    body = {"buildings_complete": True, "survey_id": features["survey_id"]}
    assert server.client.put(f"/sites/{site_id}/survey", json=body).status_code == 200


def test_a_site_not_ready_has_no_map_yet(tmp_path: Path) -> None:
    server = Server(tmp_path)
    site_id = server.client.post("/sites", json={"address_id": 7}).json()["id"]
    assert server.client.get(f"/sites/{site_id}/map").status_code == 409
    assert server.client.get("/sites/nowhere").status_code == 404


def test_the_map_draws_the_rules_on_the_title_in_lon_lat(tmp_path: Path) -> None:
    server = Server(tmp_path)
    site_id = server.build()["id"]
    layers = server.client.get(f"/sites/{site_id}/map").json()
    assert set(layers) == {
        "parcels",
        "buildings",
        "features",
        "setback",
        "halos",
        "keep_clear",
        "room",
    }
    assert len(layers["parcels"]["features"]) == 2
    (room,) = layers["room"]["features"]
    (band,) = layers["setback"]["features"]
    middle = shape(layers["parcels"]["features"][0]["geometry"]).centroid
    assert shape(room["geometry"]).contains(Point(middle.x, middle.y))
    assert band["properties"] == {"metres": 2.0}
    assert not shape(band["geometry"]).intersects(shape(room["geometry"]).buffer(-1e-7))


def test_site_builds_past_the_cap_are_refused(tmp_path: Path) -> None:
    server = Server(tmp_path, cap=1)
    assert server.client.post("/sites", json={"address_id": 7}).status_code == 202
    refused = server.client.post("/sites", json={"address_id": 8})
    assert refused.status_code == 429 and "1 site builds a day" in refused.json()["detail"]


def test_a_failed_site_is_built_again_when_asked(tmp_path: Path) -> None:
    server = Server(tmp_path)
    site_id = server.client.post("/sites", json={"address_id": 7}).json()["id"]
    server.sites_store.start(site_id)
    assert server.sites_store.recover() == 1  # as a restart mid-build leaves it
    assert server.client.get(f"/sites/{site_id}").json()["status"] == "failed"
    again = server.client.post("/sites", json={"address_id": 7}).json()
    assert again["status"] == "building"
    server.builder.run_next()
    assert server.client.get(f"/sites/{site_id}").json()["status"] == "ready"


def test_two_addresses_with_one_slug_get_two_sites(tmp_path: Path) -> None:
    store = SiteStore(tmp_path / "sites.db")
    first = store.create(1, "1 Test Street, Reefton")
    second = store.create(2, "1 Test Street, Reefton")
    assert (first.id, second.id) == ("1-test-street-reefton", "1-test-street-reefton-2")
    assert store.create(3, "1 Ōtaki Road").id == "1-otaki-road"
    since = datetime.now(UTC) - timedelta(minutes=1)
    assert len(store.created_since(since)) == 3


def test_every_rebuild_counts_against_the_cap(tmp_path: Path) -> None:
    server = Server(tmp_path, cap=2)
    site_id = server.client.post("/sites", json={"address_id": 7}).json()["id"]

    def fail_and_ask_again() -> int:  # as a restart mid-build leaves it
        server.sites_store.start(site_id)
        server.sites_store.recover()
        return server.client.post("/sites", json={"address_id": 7}).status_code

    assert fail_and_ask_again() == 202  # the day's second build
    assert fail_and_ask_again() == 429  # a third is past the cap


def test_two_requests_for_one_new_address_get_the_one_site(tmp_path: Path) -> None:
    server = Server(tmp_path)

    def ask(_: int) -> Response:
        return server.client.post("/sites", json={"address_id": 7})

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(ask, range(4)))
    assert {r.status_code for r in responses} == {202}
    assert {r.json()["id"] for r in responses} == {"1-test-street-reefton"}
