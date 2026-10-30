"""Tests for button_nz.api: design jobs over HTTP, run by the worker with a
scripted model and a fake Blender runner."""

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from button_nz.agent.conversation import Model, Observe, Turn
from button_nz.agent.loop import DesignSite, Runner
from button_nz.api.app import create_app
from button_nz.api.jobs import Illustrator, Worker
from button_nz.api.store import Store
from button_nz.blender_worker.run import BlenderError, DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.demo_site import load_demo_site
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.visual import VISUAL_MODEL, Visual, visual_client
from meshes import box

PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
GOOD = {
    "error": None,
    "triangles": box(15, 7, 0.3, 21, 12, 3.9),
    "floor_area_m2": 26.0,
    "storeys": 1,
}
NEAR = GOOD | {"triangles": box(0.5, 7, 0.3, 6.5, 12, 3.9)}  # 0.5 m from the edge


class ScriptedModel:
    def __init__(self, *replies: str | Observe) -> None:
        self.replies = list(replies)
        self.seen: list[list[Turn]] = []

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        self.seen.append(list(conversation))
        return self.replies.pop(0)


def fake_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    out_dir.mkdir(parents=True, exist_ok=True)
    png, mask = out_dir / "design.png", out_dir / "dwelling-mask.png"
    png.write_bytes(b"\x89PNG design")
    mask.write_bytes(b"\x89PNG mask")
    (out_dir / "design.py").write_text(script, encoding="utf-8")
    measurements = {"good": GOOD, "near": NEAR}[script]
    (out_dir / "measurements.json").write_text(json.dumps(measurements), encoding="utf-8")
    return DesignOutputs(measurements, out_dir / "design.py", None, png, mask)


def maskless_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    return replace(fake_runner(scene, script, out_dir), mask=None)


class FakeIllustrator:
    """Stands in for Muse Image and SAM: returns ``visual``, or raises ``error``."""

    def __init__(self, visual: Visual | None = None, error: Exception | None = None) -> None:
        self.visual, self.error = visual, error
        self.calls: list[tuple[Path, Path]] = []

    def __call__(self, render: Path, mask: Path) -> Visual:
        self.calls.append((render, mask))
        if self.error is not None:
            raise self.error
        assert self.visual is not None
        return self.visual


ACCEPTED_VISUAL = Visual(VISUAL_MODEL, True, 0.83, None, b"\x89PNG visual")


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
    raise KeyError("META_API_KEY is not set: get a Meta Model API key")


def scripted() -> Model:
    return ScriptedModel("near", "good")


class Service:
    def __init__(
        self,
        tmp_path: Path,
        model: Callable[[], Model] = scripted,
        runner: Runner = fake_runner,
        illustrator: Illustrator | None = None,
    ) -> None:
        self.store = Store(tmp_path / "button.db")
        self.worker = Worker(
            self.store,
            site=synthetic_site,
            model=model,
            runs_dir=tmp_path / "runs",
            runner=runner,
            illustrator=illustrator,
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
        "attempts/1/dwelling-mask.png",
        "attempts/2/visual.txt",
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
    assert "META_API_KEY is not set" in job["error"]


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


def test_a_symlinked_artifact_is_neither_listed_nor_served(
    service: Service, tmp_path: Path
) -> None:
    """Defence in depth: nothing untrusted can write the attempt directory, but
    if a link appeared there it must not expose the file it points at."""
    secret = tmp_path / "secret.env"
    secret.write_text("META_API_KEY=hunter2", encoding="utf-8")
    job_id = service.queue()
    service.worker.run_next()
    attempt = tmp_path / "runs" / job_id / "attempt-1"
    (attempt / "observation-9.png").symlink_to(secret)
    (attempt / "design.png").unlink()
    (attempt / "design.png").symlink_to(secret)
    files = service.client.get(f"/designs/{job_id}").json()["attempts"][0]["files"]
    assert "observation-9.png" not in files and "design.png" not in files
    for name in ("observation-9.png", "design.png"):
        response = service.client.get(f"/designs/{job_id}/attempts/1/{name}")
        assert response.status_code == 404
        assert b"hunter2" not in response.content


def test_a_finished_design_can_be_revised_in_plain_words(tmp_path: Path) -> None:
    model = ScriptedModel("near", "good", "good")
    service = Service(tmp_path, model=lambda: model)
    parent = service.queue()
    service.worker.run_next()
    response = service.client.post(
        f"/designs/{parent}/revisions", json={"instruction": "Move it away from the street."}
    )
    assert response.status_code == 202
    child = response.json()
    assert child["parent_id"] == parent and child["instruction"] == "Move it away from the street."
    assert child["brief"] == "A small studio."
    service.worker.run_next()
    seen = model.seen[-1]
    assert [t.role for t in seen][-3:] == ["design", "feedback", "user"]
    assert seen[-3].text == "good"  # the accepted attempt's script
    assert seen[-1].text == "Move it away from the street."
    assert service.client.get(f"/designs/{child['id']}").json()["status"] == "done"


def test_only_an_accepted_design_can_be_revised(tmp_path: Path) -> None:
    service = Service(tmp_path, model=lambda: ScriptedModel("near", "near", "near"))
    job_id = service.queue()
    revise = {"instruction": "Make it bigger."}
    assert service.client.post(f"/designs/{job_id}/revisions", json=revise).status_code == 409
    service.worker.run_next()  # three failed attempts: nothing accepted
    assert service.client.post(f"/designs/{job_id}/revisions", json=revise).status_code == 409
    assert service.client.post("/designs/nope/revisions", json=revise).status_code == 404
    empty = {"instruction": ""}
    assert service.client.post(f"/designs/{job_id}/revisions", json=empty).status_code == 422


def test_a_revision_of_a_revision_keeps_every_instruction(tmp_path: Path) -> None:
    model = ScriptedModel("good", "good", "good")
    service = Service(tmp_path, model=lambda: model)
    first = service.queue()
    service.worker.run_next()
    second = service.client.post(
        f"/designs/{first}/revisions", json={"instruction": "Move it away from the street."}
    ).json()["id"]
    service.worker.run_next()
    service.client.post(f"/designs/{second}/revisions", json={"instruction": "Make it bigger."})
    service.worker.run_next()
    asked = model.seen[-1][-1].text
    assert "Move it away from the street." in asked and "Make it bigger." in asked
    assert asked.index("away from the street") < asked.index("bigger")  # oldest first


def test_an_accepted_design_gets_an_ai_visual(tmp_path: Path) -> None:
    illustrator = FakeIllustrator(ACCEPTED_VISUAL)
    service = Service(tmp_path, illustrator=illustrator)
    job_id = service.queue()
    service.worker.run_next()
    attempt = tmp_path / "runs" / job_id / "attempt-2"
    assert illustrator.calls == [(attempt / "design.png", attempt / "dwelling-mask.png")]
    first, second = service.client.get(f"/designs/{job_id}").json()["attempts"]
    assert "visual.png" not in first["files"]  # only the accepted attempt is illustrated
    assert service.client.get(second["files"]["visual.png"]).content == b"\x89PNG visual"
    record = service.client.get(second["files"]["visual.json"]).json()
    assert record == {
        "model": "muse-image-1.0",
        "accepted": True,
        "iou": 0.83,
        "min_iou": 0.6,
        "reason": None,
    }


def test_a_rejected_visual_is_recorded_without_an_image(tmp_path: Path) -> None:
    moved = Visual(VISUAL_MODEL, False, 0.31, "It moved.", None)
    service = Service(tmp_path, illustrator=FakeIllustrator(moved))
    job_id = service.queue()
    service.worker.run_next()
    files = service.client.get(f"/designs/{job_id}").json()["attempts"][1]["files"]
    assert "visual.png" not in files
    record = service.client.get(files["visual.json"]).json()
    assert record["accepted"] is False and record["iou"] == 0.31
    assert record["reason"] == "It moved."


def test_a_failed_visual_leaves_the_design_as_it_was(tmp_path: Path) -> None:
    down = FakeIllustrator(error=RuntimeError("the Meta Model API is down"))
    service = Service(tmp_path, illustrator=down)
    job_id = service.queue()
    service.worker.run_next()
    job = service.client.get(f"/designs/{job_id}").json()
    assert job["status"] == "done" and job["error"] is None
    assert job["accepted_attempt"] == 2 and job["attempts"][1]["status"] == "unknown"
    files = job["attempts"][1]["files"]
    assert "visual.png" not in files
    record = service.client.get(files["visual.json"]).json()
    assert record["accepted"] is False and record["iou"] is None
    assert record["reason"] == "RuntimeError: the Meta Model API is down"


def test_an_attempt_without_a_silhouette_is_not_illustrated(tmp_path: Path) -> None:
    illustrator = FakeIllustrator(ACCEPTED_VISUAL)
    service = Service(tmp_path, runner=maskless_runner, illustrator=illustrator)
    job_id = service.queue()
    service.worker.run_next()
    assert illustrator.calls == []
    files = service.client.get(f"/designs/{job_id}").json()["attempts"][1]["files"]
    record = service.client.get(files["visual.json"]).json()
    assert record["accepted"] is False and "silhouette" in record["reason"]


def test_a_design_with_nothing_accepted_gets_no_visual(tmp_path: Path) -> None:
    illustrator = FakeIllustrator(ACCEPTED_VISUAL)
    model = ScriptedModel("near", "near", "near")
    service = Service(tmp_path, model=lambda: model, illustrator=illustrator)
    job_id = service.queue()
    service.worker.run_next()
    assert illustrator.calls == []
    for attempt in service.client.get(f"/designs/{job_id}").json()["attempts"]:
        assert not {"visual.png", "visual.json"} & set(attempt["files"])


def test_a_design_is_done_before_its_visual_is_made(tmp_path: Path) -> None:
    """The visual is extra: a restart while Muse Image works mustn't cost the
    accepted design, so the job is already done when the visual starts."""
    seen: list[tuple[str, int | None]] = []
    service: Service | None = None

    def illustrator(render: Path, mask: Path) -> Visual:
        assert service is not None
        job = service.store.get_job(job_id)
        seen.append((job.status, job.accepted_attempt))
        return ACCEPTED_VISUAL

    service = Service(tmp_path, illustrator=illustrator)
    job_id = service.queue()
    service.worker.run_next()
    assert seen == [("done", 2)]


def test_a_slow_edit_is_not_retried() -> None:
    """Each retry of a slow edit would wait again, and be billed again."""
    assert visual_client("key").max_retries == 0


def test_a_job_says_while_its_visual_is_being_made(tmp_path: Path) -> None:
    """Done, with the visual still to come: the web app keeps looking for it."""
    during: list[bool] = []
    service: Service | None = None

    def illustrator(render: Path, mask: Path) -> Visual:
        assert service is not None
        during.append(service.client.get(f"/designs/{job_id}").json()["illustrating"])
        return ACCEPTED_VISUAL

    service = Service(tmp_path, illustrator=illustrator)
    job_id = service.queue()
    service.worker.run_next()
    assert during == [True]
    assert service.client.get(f"/designs/{job_id}").json()["illustrating"] is False


def test_without_an_illustrator_no_visual_is_awaited(service: Service) -> None:
    job_id = service.queue()
    service.worker.run_next()
    assert service.client.get(f"/designs/{job_id}").json()["illustrating"] is False


def test_a_visual_cut_off_by_a_restart_is_recorded_as_such(tmp_path: Path) -> None:
    """Otherwise the job would say its visual is coming for ever."""
    service = Service(tmp_path, illustrator=FakeIllustrator(ACCEPTED_VISUAL))
    job_id = service.queue()
    service.worker.run_next()
    attempt = tmp_path / "runs" / job_id / "attempt-2"
    for name in ("visual.json", "visual.png"):  # as if the server stopped mid-visual
        (attempt / name).unlink()
    assert service.client.get(f"/designs/{job_id}").json()["illustrating"] is True
    service.worker.recover_visuals()
    assert service.client.get(f"/designs/{job_id}").json()["illustrating"] is False
    record = json.loads((attempt / "visual.json").read_text(encoding="utf-8"))
    assert record["accepted"] is False and record["reason"] == "interrupted by a restart"
