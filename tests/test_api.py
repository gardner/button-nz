"""Tests for button_nz.api: design jobs over HTTP, run by the worker with a
scripted model and a fake Blender runner."""

import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from button_nz.agent.conversation import Model, Observe, Turn
from button_nz.agent.loop import DesignSite, Runner
from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.store import Store
from button_nz.blender_worker.run import BlenderError, DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.demo_site import load_demo_site
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
GOOD = {
    "error": None,
    "faces_xy": [[[15, 7], [21, 7], [21, 12], [15, 12]]],
    "z_min": 0.3,
    "z_max": 3.9,
    "floor_area_m2": 26.0,
    "storeys": 1,
}
NEAR = GOOD | {"faces_xy": [[[0.5, 7], [6.5, 7], [6.5, 12], [0.5, 12]]]}  # 0.5 m from the edge


class ScriptedModel:
    def __init__(self, *replies: str | Observe) -> None:
        self.replies = list(replies)

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        return self.replies.pop(0)


def fake_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "design.png"
    png.write_bytes(b"\x89PNG design")
    (out_dir / "design.py").write_text(script, encoding="utf-8")
    measurements = {"good": GOOD, "near": NEAR}[script]
    return DesignOutputs(measurements, out_dir / "design.py", None, png)


def broken_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    raise BlenderError("Blender exited 1: no GPU")


def synthetic_site() -> DesignSite:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    return DesignSite(
        scene_input(grid, frame, [PARCEL]), frame, SiteContext(parcels=(PARCEL,), terrain=grid)
    )


def no_key() -> Model:
    raise KeyError("MODEL_API_KEY is not set: get a Meta Model API key")


def scripted() -> Model:
    return ScriptedModel("near", "good")


class Service:
    def __init__(
        self,
        tmp_path: Path,
        model: Callable[[], Model] = scripted,
        runner: Runner = fake_runner,
    ) -> None:
        self.store = Store(tmp_path / "button.db")
        self.worker = Worker(
            self.store, site=synthetic_site, model=model, runs_dir=tmp_path / "runs", runner=runner
        )
        self.client = TestClient(create_app(self.store, self.worker, load_demo_site()))

    def queue(self, brief: str = "A small studio.") -> str:
        response = self.client.post("/designs", json={"brief": brief})
        assert response.status_code == 202
        return str(response.json()["id"])


@pytest.fixture
def service(tmp_path: Path) -> Service:
    return Service(tmp_path)


def test_the_site_is_served_with_its_sources(service: Service) -> None:
    site = service.client.get("/site").json()
    assert site["title"] == "354613"
    assert len(site["parcels"]["features"]) == 4
    assert site["parcels"]["features"][0]["geometry"]["type"] == "Polygon"
    assert site["crs"] == "EPSG:2193"
    assert {s["licence"] for s in site["sources"].values()} >= {"CC-BY-4.0"}
    assert site["open_items"]


def test_a_design_is_queued(service: Service) -> None:
    job_id = service.queue()
    job = service.client.get(f"/designs/{job_id}").json()
    assert job["status"] == "queued"
    assert job["brief"] == "A small studio."
    assert job["allow_observations"] is True
    assert job["attempts"] == []


@pytest.mark.parametrize("body", [{}, {"brief": ""}, {"brief": "x" * 4001}])
def test_a_bad_brief_is_rejected(service: Service, body: dict[str, object]) -> None:
    assert service.client.post("/designs", json=body).status_code == 422


def test_a_finished_design_shows_every_attempt_and_its_files(service: Service) -> None:
    job_id = service.queue()
    assert service.worker.run_next()
    job = service.client.get(f"/designs/{job_id}").json()
    assert job["status"] == "done"
    assert job["accepted_attempt"] == 2
    first, second = job["attempts"]
    assert first["status"] == "fail" and "title_boundary_setback" in first["feedback"]
    assert second["status"] == "unknown"
    url = second["files"]["design.png"]
    assert url == f"/designs/{job_id}/attempts/2/design.png"
    assert service.client.get(url).content == b"\x89PNG design"


@pytest.mark.parametrize(
    "path",
    [
        "attempts/1/design.py",
        "attempts/1/measurements.json",
        "attempts/1/..%2F..%2Fbutton.db",
        "attempts/9/design.png",
        "attempts/0/design.png",
    ],
)
def test_only_listed_artifacts_can_be_fetched(service: Service, path: str) -> None:
    job_id = service.queue()
    service.worker.run_next()
    assert service.client.get(f"/designs/{job_id}/{path}").status_code == 404


def test_an_unknown_design_is_not_found(service: Service) -> None:
    assert service.client.get("/designs/nope").status_code == 404
    assert service.client.get("/designs/nope/attempts/1/design.png").status_code == 404


def test_a_missing_api_key_fails_the_job_with_the_reason(tmp_path: Path) -> None:
    service = Service(tmp_path, model=no_key)
    job_id = service.queue()
    service.worker.run_next()
    job = service.client.get(f"/designs/{job_id}").json()
    assert job["status"] == "failed"
    assert "MODEL_API_KEY is not set" in job["error"]


def test_a_blender_failure_fails_the_job(tmp_path: Path) -> None:
    service = Service(tmp_path, runner=broken_runner)
    job_id = service.queue()
    service.worker.run_next()
    job = service.client.get(f"/designs/{job_id}").json()
    assert job["status"] == "failed"
    assert "no GPU" in job["error"]


def test_the_worker_thread_runs_queued_designs(service: Service) -> None:
    service.worker.start()
    try:
        job_id = service.queue()
        deadline = time.monotonic() + 10
        while service.client.get(f"/designs/{job_id}").json()["status"] != "done":
            assert time.monotonic() < deadline, "the worker never finished the job"
            time.sleep(0.05)
    finally:
        service.worker.stop()
    assert not service.worker.run_next()  # nothing left queued
