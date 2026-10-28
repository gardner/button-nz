"""Tests for the site's aerial photograph over HTTP, for the web app's plan."""

from pathlib import Path

from fastapi.testclient import TestClient

from button_nz.api.aerial import SiteAerial, aerial_bbox
from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site
from test_api import scripted, synthetic_site

PNG = b"\x89PNG\r\n\x1a\n aerial"


def client(tmp_path: Path, aerial: SiteAerial | None) -> TestClient:
    store = Store(tmp_path / "button.db")
    worker = Worker(store, site=synthetic_site, model=scripted, runs_dir=tmp_path / "runs")
    return TestClient(create_app(store, worker, load_demo_site(), aerial=aerial))


def test_the_site_says_where_its_aerial_is_and_serves_it(tmp_path: Path) -> None:
    made: list[int] = []

    def render() -> bytes:
        made.append(1)
        return PNG

    api = client(tmp_path, SiteAerial((10.0, 20.0, 30.0, 40.0), render))
    site = api.get("/site").json()
    assert site["aerial"] == {"bbox": [10.0, 20.0, 30.0, 40.0], "url": "/site/aerial.png"}
    for _ in range(2):
        response = api.get("/site/aerial.png")
        assert response.status_code == 200 and response.content == PNG
        assert response.headers["content-type"] == "image/png"
    assert made == [1]  # read once, then kept


def test_without_an_aerial_the_site_says_so(tmp_path: Path) -> None:
    api = client(tmp_path, None)
    assert api.get("/site").json()["aerial"] is None
    assert api.get("/site/aerial.png").status_code == 404


def test_the_aerial_covers_the_site_and_a_margin_in_whole_metres() -> None:
    site = load_demo_site()
    west, south, east, north = aerial_bbox(site, margin_m=10.0)
    e_west, e_south, e_east, e_north = site.extent_nztm
    assert west <= e_west - 10 and south <= e_south - 10
    assert east >= e_east + 10 and north >= e_north + 10
    assert all(v == int(v) for v in (west, south, east, north))
