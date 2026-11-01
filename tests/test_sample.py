"""Tests for button_nz.sample: packaging a design, and the designs it revises,
as the submission's sample artifacts."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from button_nz.api.store import AttemptRecord, Store
from button_nz.demo_site import DEMO_SITE_DIR
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
    site_id: str | None = None,
) -> str:
    """A done job whose attempt 1 failed and attempt 2 (if any) was accepted,
    recording the survey's decisions as they were when it ran, as the worker does."""
    job = store.create_job("A small studio.", True, parent, instruction, site_id=site_id)
    store.mark_running(job.id)
    folder = runs.parent if site_id is None else runs.parent / "sites" / site_id
    survey = Survey.read(folder / SURVEY_FILE)
    assert survey is not None
    record_survey(store, survey, runs / job.id)
    for number in (1, 2):
        store.add_attempt(AttemptRecord(job.id, number, "fail", "too close", ()))
        folder = runs / job.id / f"attempt-{number}"
        (folder / "script").mkdir(parents=True)
        for name in (*LISTED, "attempt.json", "dwelling-mask.png", "observation-1.png"):
            (folder / name).write_text(f"{job.id} {number} {name}", encoding="utf-8")
        (folder / "script" / "design.blend").write_bytes(b"BLENDER")
    store.mark_done(job.id, accepted)
    return job.id


def record_survey(store: Store, survey: Survey, run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    used = {
        "survey_id": survey.id,
        "decisions": store.decisions(survey.id),
        "buildings_complete": store.buildings_complete(survey.id),
    }
    (run / "survey.json").write_text(json.dumps(used), encoding="utf-8")


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


def test_the_survey_is_packed_with_the_decisions_the_design_was_checked_against(
    data: Path,
) -> None:
    store = Store(data / "button.db")
    found = Survey.read(data / SURVEY_FILE)
    assert found is not None
    store.decide(found.id, "1", "ignore")
    store.set_buildings_complete(found.id, True)
    job = finished(store, data / "runs", 2)
    store.decide(found.id, "2", "keep_clear")  # after it ran: not what it was checked against
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


def test_a_missing_accepted_attempt_is_refused_not_packed_without(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    accepted = data / "runs" / job / "attempt-2"
    for path in sorted(accepted.rglob("*"), reverse=True):
        path.rmdir() if path.is_dir() else path.unlink()
    accepted.rmdir()
    with pytest.raises(SampleError, match="attempt-2"):
        pack(data, job, "the owner", data / "sample.zip")
    assert not (data / "sample.zip").exists()


def test_an_accepted_attempt_missing_a_file_is_refused(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    (data / "runs" / job / "attempt-2" / "design.glb").unlink()
    with pytest.raises(SampleError, match="design.glb"):
        pack(data, job, "the owner", data / "sample.zip")


def test_a_linked_folder_is_refused_not_skipped(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    script = data / "runs" / job / "attempt-2" / "script"
    (script / "design.blend").rename(data / "design.blend")
    script.rmdir()
    elsewhere = data / "elsewhere"
    elsewhere.mkdir()
    (data / "design.blend").rename(elsewhere / "design.blend")
    script.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(SampleError, match="link"):
        pack(data, job, "the owner", data / "sample.zip")


def test_designs_checked_against_different_decisions_are_refused(data: Path) -> None:
    store = Store(data / "button.db")
    found = Survey.read(data / SURVEY_FILE)
    assert found is not None
    original = finished(store, data / "runs", 2)
    store.decide(found.id, "1", "building")
    revised = finished(store, data / "runs", 2, original, "Move it north.")
    with pytest.raises(SampleError, match="different"):
        pack(data, revised, "the owner", data / "sample.zip")
    assert not (data / "sample.zip").exists()


def test_a_revision_recorded_with_its_buildings_packs_with_an_older_record(data: Path) -> None:
    store = Store(data / "button.db")
    original = finished(store, data / "runs", 2)  # recorded before buildings were kept
    revised = finished(store, data / "runs", 2, original, "Move it north.")
    record = data / "runs" / revised / "survey.json"
    record.write_text(json.dumps({**json.loads(record.read_text()), "buildings": []}))
    pack(data, revised, "the owner", data / "sample.zip")  # same survey, same decisions
    assert "design-2/attempt-2/design.glb" in names(data / "sample.zip")


def test_a_design_with_no_record_of_its_survey_is_refused(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    (data / "runs" / job / "survey.json").unlink()
    with pytest.raises(SampleError, match="no record"):
        pack(data, job, "the owner", data / "sample.zip")


def test_a_survey_replaced_since_the_design_ran_is_refused(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    write_survey(data / SURVEY_FILE, "tree", "tree", "shed")
    with pytest.raises(SampleError, match="changed"):
        pack(data, job, "the owner", data / "sample.zip")


def test_a_linked_run_folder_is_refused_not_followed(data: Path) -> None:
    store = Store(data / "button.db")
    job = finished(store, data / "runs", 2)
    run = data / "runs" / job
    run.rename(data / "elsewhere")
    run.symlink_to(data / "elsewhere", target_is_directory=True)
    with pytest.raises(SampleError, match="link"):
        pack(data, job, "the owner", data / "sample.zip")


def built_site(data: Path) -> str:
    """A site built for an address: the demo's manifest renamed, its own survey."""
    folder = data / "sites" / "1-other-street"
    shutil.copytree(DEMO_SITE_DIR, folder)
    manifest = json.loads((folder / "site.json").read_text())
    (folder / "site.json").write_text(json.dumps({**manifest, "name": "1 Other Street"}))
    write_survey(folder / SURVEY_FILE, "tree")
    return folder.name


def test_a_design_on_a_built_site_is_packed_with_that_site_and_its_survey(data: Path) -> None:
    store = Store(data / "button.db")
    site_id = built_site(data)
    original = finished(store, data / "runs", 2, site_id=site_id)
    revised = finished(store, data / "runs", 2, original, "Move it north.", site_id=site_id)
    pack(data, revised, "the owner", data / "sample.zip")
    with zipfile.ZipFile(data / "sample.zip") as z:
        manifest = json.loads(z.read("sample.json"))
        survey = json.loads(z.read("survey.json"))
    assert manifest["site"]["name"] == "1 Other Street"
    expected = Survey.read(data / "sites" / site_id / SURVEY_FILE)
    assert expected is not None and survey["survey_id"] == expected.id


def test_designs_on_different_sites_are_refused(data: Path) -> None:
    store = Store(data / "button.db")
    original = finished(store, data / "runs", 2)
    revised = finished(store, data / "runs", 2, original, "Move it.", site_id=built_site(data))
    with pytest.raises(SampleError, match="different sites"):
        pack(data, revised, "the owner", data / "sample.zip")


def test_a_suggested_decision_is_packed_as_the_surveys_not_the_owners(data: Path) -> None:
    store = Store(data / "button.db")
    found = Survey.read(data / SURVEY_FILE)
    assert found is not None
    store.decide(found.id, "1", "building")
    job = finished(store, data / "runs", 2)
    used = json.loads((data / "runs" / job / "survey.json").read_text())
    used["decisions"]["2"] = "keep_clear"  # the survey's suggestion, as the worker records it
    used["suggested"] = ["2"]
    (data / "runs" / job / "survey.json").write_text(json.dumps(used), encoding="utf-8")
    pack(data, job, "the owner", data / "sample.zip")
    with zipfile.ZipFile(data / "sample.zip") as z:
        survey = json.loads(z.read("survey.json"))
        readme = z.read("README.md").decode()
    props = [f["properties"] for f in survey["features"]]
    assert [(p["decision"], p["suggested"]) for p in props] == [
        ("building", False),
        ("keep_clear", True),
    ]
    assert "suggested" in readme


def test_designs_checked_against_a_suggestion_and_an_owners_choice_differ(data: Path) -> None:
    store = Store(data / "button.db")
    found = Survey.read(data / SURVEY_FILE)
    assert found is not None
    store.decide(found.id, "2", "keep_clear")  # the owner's own choice
    original = finished(store, data / "runs", 2)
    revised = finished(store, data / "runs", 2, original, "Move it north.")
    used = json.loads((data / "runs" / original / "survey.json").read_text())
    used["suggested"] = ["2"]  # the same decision, but the survey's suggestion then
    (data / "runs" / original / "survey.json").write_text(json.dumps(used), encoding="utf-8")
    with pytest.raises(SampleError, match="different survey decisions"):
        pack(data, revised, "the owner", data / "sample.zip")
