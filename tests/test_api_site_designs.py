"""Tests for designing on any site (#86 step 2): a design names its site, the
worker designs there, and the design is served with its checks and its map."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapely
from fastapi import HTTPException
from numpy.typing import NDArray
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from button_nz.blender_worker.run import DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput
from button_nz.sites.registry import DEMO_SITE_ID
from meshes import box
from test_api import ScriptedModel
from test_api_sites import Server

# In the built site's local frame (centred on its two 40 m x 30 m parcels): an
# 11 m x 5 m box inside the first parcel, 3 m from the title's west edge and
# 6 m from the line between the parcels. A 9 m x 3.5 m prefab fits inside it.
INSIDE = {
    "error": None,
    "triangles": box(-17, -3, 0.3, -6, 2, 3.9),
    "floor_area_m2": 45.0,
    "storeys": 1,
}


def runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scene.json").write_text(json.dumps(scene), encoding="utf-8")  # as run.py does
    png = out_dir / "design.png"
    png.write_bytes(b"\x89PNG design")
    (out_dir / "design.py").write_text(script, encoding="utf-8")
    (out_dir / "measurements.json").write_text(json.dumps(INSIDE), encoding="utf-8")
    return DesignOutputs(INSIDE, out_dir / "design.py", None, png, None)


def designing(tmp_path: Path) -> tuple[Server, str]:
    model = ScriptedModel("inside", "inside")
    server = Server(tmp_path, model=lambda: model, runner=runner)
    return server, server.build()["id"]


def design(server: Server, site_id: str) -> dict[str, Any]:
    created = server.client.post("/designs", json={"brief": "A studio.", "site_id": site_id})
    assert created.status_code == 202, created.text
    assert server.worker.run_next()
    return server.client.get(f"/designs/{created.json()['id']}").json()


def test_a_design_is_made_on_the_site_it_names(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    assert job["site_id"] == site_id
    assert job["accepted_attempt"] == 1
    checks = {c["name"]: c for c in job["attempts"][0]["checks"]}
    assert checks["within_site"]["status"] == "pass"  # on the built site's own title
    setback = checks["title_boundary_setback"]
    assert abs(setback["measured"]["distance_m"] - 3.0) < 0.05 and "Schedule 1A" in setback["rule"]


def test_an_attempt_without_its_trace_says_its_checks_are_unknown(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    (tmp_path / "runs" / job["id"] / "attempt-1" / "attempt.json").unlink()
    (attempt,) = server.client.get(f"/designs/{job['id']}").json()["attempts"]
    assert attempt["checks"] is None  # not [] : that would say no check ran


def test_a_design_without_a_site_is_on_the_demo_site(tmp_path: Path) -> None:
    server = Server(tmp_path)
    created = server.client.post("/designs", json={"brief": "A studio."}).json()
    assert created["site_id"] == DEMO_SITE_ID


def test_a_design_on_a_site_that_isnt_ready_or_doesnt_exist_is_refused(tmp_path: Path) -> None:
    server = Server(tmp_path)
    building = server.client.post("/sites", json={"address_id": 7}).json()["id"]
    body = {"brief": "A studio.", "site_id": building}
    assert server.client.post("/designs", json=body).status_code == 409
    body["site_id"] = "nowhere"
    assert server.client.post("/designs", json=body).status_code == 404


def test_a_revision_stays_on_its_designs_site(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    revised = server.client.post(
        f"/designs/{job['id']}/revisions", json={"instruction": "Move it north."}
    ).json()
    assert revised["site_id"] == site_id


def test_a_designs_map_draws_its_walls_and_distances_in_lon_lat(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    layers = server.client.get(f"/designs/{job['id']}/map").json()
    (walls,) = layers["walls"]["features"]
    (outline,) = layers["outline"]["features"]
    lon, lat = walls["geometry"]["coordinates"][0][0]
    assert 171 < lon < 172 and -43 < lat < -42
    assert shape(outline["geometry"]).covers(shape(walls["geometry"]).buffer(-1e-9))
    distances = {d["properties"]["check"]: d["properties"] for d in layers["distances"]["features"]}
    setback = distances["title_boundary_setback"]
    assert setback["required"] == 2.0
    assert abs(setback["metres"] - 3.0) < 0.05  # 3 m in from the title's west edge
    assert abs(distances["section_boundary_setback"]["metres"] - 6.0) < 0.05


def test_the_map_and_products_stand_where_the_designs_scene_put_them(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)

    def drawn() -> list[BaseGeometry]:
        layers = server.client.get(f"/designs/{job['id']}/map").json()
        (product, *_) = server.client.get(f"/designs/{job['id']}/products").json()["fits"]
        (placed,) = product["placed_footprint"]["features"]
        walls = layers["walls"]["features"][0]["geometry"]
        line = layers["distances"]["features"][0]["geometry"]
        return [nztm(shape(g)) for g in (walls, line, placed["geometry"])]

    before = drawn()
    scene_path = tmp_path / "runs" / job["id"] / "attempt-1" / "scene.json"
    scene = json.loads(scene_path.read_text())
    x, y = scene["frame"]["origin_nztm"]
    scene["frame"]["origin_nztm"] = [x + 100, y]  # the site's manifest no longer says this
    scene_path.write_text(json.dumps(scene))
    after = drawn()
    moved = [a.centroid.x - b.centroid.x for a, b in zip(after, before, strict=True)]
    assert moved == pytest.approx([100, 100, 100], abs=0.01)  # walls, title line, product


def test_a_designs_map_needs_only_its_own_snapshot_not_the_site_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)

    def gone(site_id: str) -> None:
        raise HTTPException(409, f"site {site_id} is failed, not ready")

    monkeypatch.setattr(server.sites, "site", gone)  # rebuilt, failed or removed since
    layers = server.client.get(f"/designs/{job['id']}/map")
    assert layers.status_code == 200 and layers.json()["unknown"] == []


def test_a_design_with_no_accepted_attempt_has_no_map(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    created = server.client.post("/designs", json={"brief": "A studio.", "site_id": site_id})
    assert server.client.get(f"/designs/{created.json()['id']}/map").status_code == 409


def test_each_fitting_product_says_where_it_would_stand(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    products = server.client.get(f"/designs/{job['id']}/products").json()
    walls = shape(
        server.client.get(f"/designs/{job['id']}/map").json()["walls"]["features"][0]["geometry"]
    )
    assert products["fits"], "an 11 m x 5 m footprint holds a 9 m x 3.5 m prefab"
    for product in products["fits"]:
        (placed,) = product["placed_footprint"]["features"]
        assert walls.buffer(1e-6).covers(shape(placed["geometry"]))


def test_a_designs_record_keeps_the_buildings_it_was_checked_against(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    record = json.loads((tmp_path / "runs" / job["id"] / "survey.json").read_text())
    assert record["buildings"] == []  # nothing confirmed on the built site's survey
    assert server.client.get(f"/designs/{job['id']}/map").json()["unknown"] == []


def nztm(geometry: BaseGeometry) -> BaseGeometry:
    to_nztm = Transformer.from_crs(4326, 2193, always_xy=True)

    def project(xy: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.column_stack(to_nztm.transform(xy[:, 0], xy[:, 1]))

    return shapely.transform(geometry, project)


def test_a_courtyard_building_is_measured_whole_as_the_evaluator_does(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    layers = server.client.get(f"/designs/{job['id']}/map").json()
    walls = nztm(shape(layers["walls"]["features"][0]["geometry"]))
    record_path = tmp_path / "runs" / job["id"] / "survey.json"
    record = json.loads(record_path.read_text())
    yard = walls.buffer(5.0)  # a courtyard round the whole design, its walls 5 m off
    record["buildings"] = [mapping(yard.buffer(3.0).difference(yard))]
    record_path.write_text(json.dumps(record))
    layers = server.client.get(f"/designs/{job['id']}/map").json()
    distances = {d["properties"]["check"]: d["properties"] for d in layers["distances"]["features"]}
    # the evaluator keeps each building's outer ring: the design stands inside it
    assert distances["building_separation"]["metres"] == 0.0


def test_an_older_record_that_confirmed_no_buildings_needs_no_survey(tmp_path: Path) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    record_path = tmp_path / "runs" / job["id"] / "survey.json"
    record = json.loads(record_path.read_text())
    del record["buildings"]  # recorded before buildings were kept
    record["survey_id"] = "a survey since replaced"
    record["decisions"] = {"1": "keep_clear"}  # no building among them
    record_path.write_text(json.dumps(record))
    assert server.client.get(f"/designs/{job['id']}/map").json()["unknown"] == []


def test_a_design_whose_record_is_missing_says_its_buildings_are_unknown(
    tmp_path: Path,
) -> None:
    server, site_id = designing(tmp_path)
    job = design(server, site_id)
    (tmp_path / "runs" / job["id"] / "survey.json").unlink()  # a run made before records
    layers = server.client.get(f"/designs/{job['id']}/map").json()
    assert [u["check"] for u in layers["unknown"]] == ["building_separation"]
    checks = {d["properties"]["check"] for d in layers["distances"]["features"]}
    assert "building_separation" not in checks


def test_only_a_few_design_sites_are_kept_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from button_nz.api import sites as module

    server, _ = designing(tmp_path)
    sites = server.sites
    read: list[str] = []

    def reading(site: str) -> str:  # stands in for reading the site's terrain
        read.append(site)
        return site

    def no_survey(site_id: str) -> tuple[None, None]:
        return None, None

    def same(site_id: str) -> str:
        return site_id

    monkeypatch.setattr(sites, "site", same)
    monkeypatch.setattr(sites, "survey", no_survey)
    monkeypatch.setattr(module, "design_site", reading)
    for n in range(module.DESIGN_SITES_KEPT + 2):
        sites.design_site(f"site-{n}")
    sites.design_site("site-0")  # dropped as the oldest: read again
    assert read.count("site-0") == 2
    sites.design_site(f"site-{module.DESIGN_SITES_KEPT + 1}")  # the newest: still kept
    assert read.count(f"site-{module.DESIGN_SITES_KEPT + 1}") == 1
