"""Tests for confirming surveyed site features over HTTP, and their use in designs."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from button_nz.agent.loop import DesignSite
from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site
from button_nz.perception.confirm import Decision, Survey, confirmed
from test_api import ScriptedModel, Service, fake_runner, synthetic_site


def square(x: float, y: float, size: float) -> dict[str, Any]:
    ring = [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]
    return {"type": "Polygon", "coordinates": [ring]}


def write_survey(path: Path, *concepts: str) -> None:
    """One feature per concept, 6 m squares in a row from (30, 12) NZTM."""
    features = [
        {
            "type": "Feature",
            "id": str(n),
            "properties": {"concept": concept, "status": "agrees"},
            "geometry": square(30.0 - 8 * (n - 1), 12.0, 6.0) if n < 3 else square(2, 2, 2),
        }
        for n, concept in enumerate(concepts, 1)
    ]
    collection = {"type": "FeatureCollection", "crs": "EPSG:2193", "features": features}
    path.write_text(json.dumps(collection), encoding="utf-8")


class Surveyed(Service):
    """The service with a survey at ``DATA/survey.geojson``."""

    def __init__(self, tmp_path: Path, model: ScriptedModel | None = None) -> None:
        self.model = model or ScriptedModel("good")
        self.survey = tmp_path / "survey.geojson"
        self.store = Store(tmp_path / "button.db")
        self.worker = Worker(
            self.store,
            site=synthetic_site,
            model=lambda: self.model,
            runs_dir=tmp_path / "runs",
            runner=fake_runner,
            survey=self.survey,
        )
        app = create_app(self.store, self.worker, load_demo_site(), survey=self.survey)
        self.client = TestClient(app)


@pytest.fixture
def surveyed(tmp_path: Path) -> Surveyed:
    return Surveyed(tmp_path)


def test_without_a_survey_the_features_are_not_found(surveyed: Surveyed) -> None:
    response = surveyed.client.get("/site/features")
    assert response.status_code == 404 and "survey" in response.json()["detail"]


def test_surveyed_features_are_listed_undecided(surveyed: Surveyed) -> None:
    write_survey(surveyed.survey, "shed", "tree")
    body = surveyed.client.get("/site/features").json()
    assert body["survey_id"] and body["crs"] == "EPSG:2193"
    assert [f["properties"]["decision"] for f in body["features"]] == [None, None]


def test_a_decision_is_recorded_and_shown(surveyed: Surveyed) -> None:
    write_survey(surveyed.survey, "shed", "tree")
    response = surveyed.client.put("/site/features/1", json={"decision": "building"})
    assert response.status_code == 200
    assert response.json()["properties"]["decision"] == "building"
    shed, tree = surveyed.client.get("/site/features").json()["features"]
    assert shed["properties"]["decision"] == "building"
    assert tree["properties"]["decision"] is None


@pytest.mark.parametrize(
    ("feature", "body", "code"),
    [("9", {"decision": "building"}, 404), ("1", {"decision": "demolish"}, 422)],
)
def test_bad_decisions_are_refused(
    surveyed: Surveyed, feature: str, body: dict[str, str], code: int
) -> None:
    write_survey(surveyed.survey, "shed")
    assert surveyed.client.put(f"/site/features/{feature}", json=body).status_code == code


def test_decisions_belong_to_the_survey_they_were_made_on(surveyed: Surveyed) -> None:
    """A new survey may number different things the same: nothing carries over."""
    write_survey(surveyed.survey, "shed")
    surveyed.client.put("/site/features/1", json={"decision": "building"})
    write_survey(surveyed.survey, "tree")
    (tree,) = surveyed.client.get("/site/features").json()["features"]
    assert tree["properties"]["decision"] is None


def test_a_design_keeps_clear_of_what_was_confirmed(surveyed: Surveyed) -> None:
    write_survey(surveyed.survey, "shed", "tree", "car")
    surveyed.client.put("/site/features/1", json={"decision": "building"})
    surveyed.client.put("/site/features/2", json={"decision": "keep_clear"})
    surveyed.client.put("/site/features/3", json={"decision": "ignore"})
    complete = surveyed.client.put("/site/survey", json={"buildings_complete": True})
    assert complete.status_code == 200
    job = surveyed.queue()
    surveyed.worker.run_next()
    prompt = surveyed.model.seen[0][0].text
    assert "existing buildings" in prompt and "(30.00, 12.00)" in prompt
    assert "kept clear" in prompt and "(22.00, 12.00)" in prompt
    assert "(2.00, 2.00)" not in prompt  # the ignored car
    (attempt,) = surveyed.client.get(f"/designs/{job}").json()["attempts"]
    assert "building_separation: pass" in attempt["feedback"]


def test_without_the_list_confirmed_complete_separation_stays_unknown(
    surveyed: Surveyed,
) -> None:
    """A listed building only shows how close that one is: another could be closer."""
    write_survey(surveyed.survey, "shed")
    surveyed.client.put("/site/features/1", json={"decision": "building"})
    job = surveyed.queue()
    surveyed.worker.run_next()
    (attempt,) = surveyed.client.get(f"/designs/{job}").json()["attempts"]
    assert "building_separation: unknown" in attempt["feedback"]


def test_the_list_cannot_be_complete_while_a_possible_building_is_undecided(
    surveyed: Surveyed,
) -> None:
    write_survey(surveyed.survey, "tree", "shed")
    surveyed.client.put("/site/features/1", json={"decision": "keep_clear"})
    refused = surveyed.client.put("/site/survey", json={"buildings_complete": True})
    assert refused.status_code == 409 and "2" in refused.json()["detail"]
    surveyed.client.put("/site/features/2", json={"decision": "ignore"})
    accepted = surveyed.client.put("/site/survey", json={"buildings_complete": True})
    assert accepted.status_code == 200
    assert surveyed.client.get("/site/features").json()["buildings_complete"] is True


def test_a_new_survey_is_not_confirmed_complete(surveyed: Surveyed) -> None:
    write_survey(surveyed.survey, "tree")
    surveyed.client.put("/site/survey", json={"buildings_complete": True})
    write_survey(surveyed.survey, "shed")
    assert surveyed.client.get("/site/features").json()["buildings_complete"] is False


def test_confirmed_outlines_become_the_site_context(tmp_path: Path) -> None:
    path = tmp_path / "survey.geojson"
    write_survey(path, "shed", "tree")
    survey = Survey.read(path)
    assert survey is not None
    decisions = {"1": Decision.BUILDING, "2": Decision.KEEP_CLEAR}
    site: DesignSite = confirmed(synthetic_site(), survey, decisions, complete=True)
    assert site.context.buildings_confirmed
    (building,) = site.context.confirmed_buildings
    (garden,) = site.context.preservation_areas
    assert building[0] == (30.0, 12.0) and garden[0] == (22.0, 12.0)
