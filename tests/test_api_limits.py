"""Tests for serving the API in public: a cap on design runs a day, and a
survey fixed as someone decided it."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from button_nz.api.app import create_app
from button_nz.api.fixed import FixedSurvey, SurveyReplaced, read_fixed
from button_nz.api.jobs import Worker
from button_nz.api.limits import DailyCap
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site
from button_nz.perception.confirm import Survey
from test_api import fake_runner, scripted, synthetic_site
from test_api_features import write_survey

ORIGINAL = {"brief": "A small studio."}


class Clock:
    """The time, moved on by ``ahead`` (jobs are stamped with the real time)."""

    def __init__(self) -> None:
        self.ahead = timedelta()

    def __call__(self) -> datetime:
        return datetime.now(UTC) + self.ahead


def client(
    tmp_path: Path,
    cap: int | None = None,
    clock: Clock | None = None,
    decided_by: str | None = None,
) -> tuple[TestClient, Worker]:
    store = Store(tmp_path / "button.db")
    survey = tmp_path / "survey.geojson"
    write_survey(survey, "shed", "tree")
    # Fixed, it is pinned to the survey decided: the one written here.
    fixed = None if decided_by is None else FixedSurvey(decided_by, survey_id(survey))
    worker = Worker(
        store,
        site=synthetic_site,
        model=scripted,
        runs_dir=tmp_path / "runs",
        runner=fake_runner,
        survey=survey,
        fixed_survey=fixed,
    )
    daily = None if cap is None else DailyCap(store.created_since, cap, clock=clock or Clock())
    app = create_app(store, worker, load_demo_site(), survey=survey, cap=daily, fixed_survey=fixed)
    return TestClient(app), worker


def survey_id(path: Path) -> str:
    found = Survey.read(path)
    assert found is not None
    return found.id


def test_designs_past_the_cap_wait_until_the_oldest_is_a_day_old(tmp_path: Path) -> None:
    clock = Clock()
    api, _ = client(tmp_path, cap=2, clock=clock)
    assert api.post("/designs", json=ORIGINAL).status_code == 202
    assert api.post("/designs", json=ORIGINAL).status_code == 202
    refused = api.post("/designs", json=ORIGINAL)
    assert refused.status_code == 429
    assert "2 design runs a day" in refused.json()["detail"]
    assert 0 < int(refused.headers["retry-after"]) <= 24 * 3600
    clock.ahead = timedelta(hours=24, seconds=1)
    assert api.post("/designs", json=ORIGINAL).status_code == 202


def test_revisions_count_towards_the_cap(tmp_path: Path) -> None:
    api, worker = client(tmp_path, cap=2)
    job_id = api.post("/designs", json=ORIGINAL).json()["id"]
    assert worker.run_next()
    revise = f"/designs/{job_id}/revisions"
    assert api.post(revise, json={"instruction": "Move it north."}).status_code == 202
    assert api.post(revise, json={"instruction": "Move it south."}).status_code == 429
    assert api.post("/designs", json=ORIGINAL).status_code == 429


def test_a_refused_design_is_not_queued(tmp_path: Path) -> None:
    api, worker = client(tmp_path, cap=1)
    api.post("/designs", json=ORIGINAL)
    api.post("/designs", json=ORIGINAL)
    assert worker.run_next()
    assert not worker.run_next()


def test_without_a_cap_designs_are_not_limited(tmp_path: Path) -> None:
    api, _ = client(tmp_path)
    assert all(api.post("/designs", json=ORIGINAL).status_code == 202 for _ in range(5))


def test_a_fixed_survey_says_who_decided_it_and_refuses_changes(tmp_path: Path) -> None:
    api, _ = client(tmp_path, decided_by="the owner, on 31 October 2026")
    features = api.get("/site/features").json()
    assert features["fixed"] is True
    assert features["decided_by"] == "the owner, on 31 October 2026"
    survey_id = features["survey_id"]
    change = api.put("/site/features/1", json={"decision": "ignore", "survey_id": survey_id})
    assert change.status_code == 403
    assert "the owner, on 31 October 2026" in change.json()["detail"]
    complete = api.put("/site/survey", json={"buildings_complete": True, "survey_id": survey_id})
    assert complete.status_code == 403


def test_an_open_survey_can_be_decided(tmp_path: Path) -> None:
    api, _ = client(tmp_path)
    features = api.get("/site/features").json()
    assert features["fixed"] is False
    assert features["decided_by"] is None
    body = {"decision": "ignore", "survey_id": features["survey_id"]}
    assert api.put("/site/features/1", json=body).status_code == 200


def test_a_fixed_survey_replaced_on_disk_is_refused_not_served_undecided(tmp_path: Path) -> None:
    api, _ = client(tmp_path, decided_by="the owner")
    pinned = api.get("/site/features").json()["survey_id"]
    write_survey(tmp_path / "survey.geojson", "tree", "shed", "tree")  # a new survey's id
    refused = api.get("/site/features")
    assert refused.status_code == 409
    assert pinned in refused.json()["detail"] and "the owner" in refused.json()["detail"]


def test_a_design_on_a_replaced_fixed_survey_fails_with_why(tmp_path: Path) -> None:
    api, worker = client(tmp_path, decided_by="the owner")
    write_survey(tmp_path / "survey.geojson", "tree")
    job = api.post("/designs", json=ORIGINAL).json()
    assert worker.run_next()
    failed = api.get(f"/designs/{job['id']}").json()
    assert failed["status"] == "failed" and "fixed" in failed["error"]


def test_the_fixed_survey_is_read_once_and_that_reading_is_what_is_used(tmp_path: Path) -> None:
    path = tmp_path / "survey.geojson"
    write_survey(path, "shed", "tree")
    fixed = FixedSurvey("the owner", survey_id(path))
    checked = read_fixed(path, fixed)
    write_survey(path, "tree")  # replaced after the check: the caller keeps what it checked
    assert checked is not None and checked.id == fixed.survey_id
    with pytest.raises(SurveyReplaced, match=fixed.survey_id):
        read_fixed(path, fixed)
