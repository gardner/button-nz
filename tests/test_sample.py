"""Tests for button_nz.sample: packaging a design, and the designs it revises,
as the submission's sample artifacts."""

import json
import zipfile
from pathlib import Path

import pytest

from button_nz.api.store import AttemptRecord, Store
from button_nz.perception.confirm import Survey
from button_nz.perception.survey import SURVEY_FILE
from button_nz.sample import SampleError, pack
from test_api_features import write_survey

LISTED = ("scene.json", "design.py", "design.glb", "design.png", "measurements.json")


def finished(
    store: Store,
    runs: Path,
    accepted: int | None,
    parent: str | None = None,
    instruction: str | None = None,
) -> str:
    """A done job whose attempt 1 failed and attempt 2 (if any) was accepted."""
    job = store.create_job("A small studio.", True, parent, instruction)
    store.mark_running(job.id)
    for number in (1, 2):
        store.add_attempt(AttemptRecord(job.id, number, "fail", "too close", ()))
        folder = runs / job.id / f"attempt-{number}"
        (folder / "script").mkdir(parents=True)
        for name in (*LISTED, "attempt.json", "dwelling-mask.png", "observation-1.png"):
            (folder / name).write_text(f"{job.id} {number} {name}", encoding="utf-8")
        (folder / "script" / "design.blend").write_bytes(b"BLENDER")
    store.mark_done(job.id, accepted)
    return job.id


@pytest.fixture
def data(tmp_path: Path) -> Path:
    write_survey(tmp_path / SURVEY_FILE, "shed", "tree")
    return tmp_path


def names(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as z:
        return set(z.namelist())


def test_a_revision_is_packed_after_the_design_it_revises(data: Path) -> None:
    store = Store(data / "button.db")
    original = finished(store, data / "runs", 2)
    revised = finished(store, data / "runs", 2, original, "Move it north.")
    out = data / "sample.zip"
    pack(data, revised, "the owner", out)
    packed = names(out)
    assert "design-1/attempt-2/design.glb" in packed
    assert "design-2/attempt-2/script/design.blend" in packed
    assert "design-2/attempt-1/observation-1.png" in packed
    assert not any(name.endswith("dwelling-mask.png") for name in packed)
    with zipfile.ZipFile(out) as z:
        assert z.read("design-1/attempt-2/design.py") == f"{original} 2 design.py".encode()
        manifest = json.loads(z.read("sample.json"))
    assert [d["id"] for d in manifest["designs"]] == [original, revised]
    assert manifest["designs"][1]["instruction"] == "Move it north."
    assert manifest["designs"][1]["accepted_attempt"] == 2
    assert manifest["survey"]["decided_by"] == "the owner"


def test_the_survey_is_packed_with_its_decisions(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    found = Survey.read(data / SURVEY_FILE)
    assert found is not None
    store.decide(found.id, "1", "ignore")
    store.set_buildings_complete(found.id, True)
    pack(data, job, "the owner", data / "sample.zip")
    with zipfile.ZipFile(data / "sample.zip") as z:
        survey = json.loads(z.read("survey.json"))
        readme = z.read("README.md").decode()
    assert survey["buildings_complete"] is True
    assert [f["properties"]["decision"] for f in survey["features"]] == ["ignore", None]
    assert "the owner" in readme and "CC-BY-4.0" in readme


def test_a_design_without_an_accepted_attempt_is_refused(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", None)
    with pytest.raises(SampleError, match="no accepted attempt"):
        pack(data, job, "the owner", data / "sample.zip")
    assert not (data / "sample.zip").exists()


def test_a_linked_file_is_refused_not_followed(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    render = data / "runs" / job / "attempt-2" / "design.png"
    render.unlink()
    render.symlink_to(data / "button.db")
    with pytest.raises(SampleError, match="link"):
        pack(data, job, "the owner", data / "sample.zip")
