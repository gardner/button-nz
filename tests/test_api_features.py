"""Tests for confirming surveyed site features over HTTP, and their use in designs."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response  # what TestClient returns

from button_nz.agent.loop import DesignSite
from button_nz.api.app import create_app
from button_nz.api.jobs import Worker
from button_nz.api.store import Store
from button_nz.demo_site import load_demo_site
from button_nz.perception.confirm import Decision, SiteDecisions, Survey, confirmed
from test_api import ScriptedModel, Service, fake_runner, synthetic_site


def square(x: float, y: float, size: float) -> dict[str, Any]:
    ring = [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]
    return {"type": "Polygon", "coordinates": [ring]}


def write_survey(path: Path, *concepts: str, status: str = "conflict") -> None:
    """One feature per concept, 6 m squares in a row from (30, 12) NZTM. Each
    is one the LiDAR disputes, unless ``status`` says otherwise: the survey
    suggests no decision for those, so they start undecided."""
    features = [
        {
            "type": "Feature",
            "id": str(n),
            "properties": {"concept": concept, "status": status},
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


def decide(surveyed: Surveyed, feature: str, body: dict[str, str]) -> Response:
    """PUT a decision, made on the survey being served."""
    survey_id = surveyed.client.get("/site/features").json()["survey_id"]
    return surveyed.client.put(f"/site/features/{feature}", json=body | {"survey_id": survey_id})


def list_complete(surveyed: Surveyed) -> Response:
    survey_id = surveyed.client.get("/site/features").json()["survey_id"]
    body = {"buildings_complete": True, "survey_id": survey_id}
    return surveyed.client.put("/site/survey", json=body)


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
    response = decide(surveyed, "1", {"decision": "building"})
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
    assert decide(surveyed, feature, body).status_code == code


def test_a_decision_made_on_an_older_survey_is_refused(surveyed: Surveyed) -> None:
    """The page was loaded before a new survey was written: its feature 1 may be
    something else now, so the decision must not land on it."""
    write_survey(surveyed.survey, "shed")
    stale = surveyed.client.get("/site/features").json()["survey_id"]
    write_survey(surveyed.survey, "tree")
    body = {"decision": "building", "survey_id": stale}
    response = surveyed.client.put("/site/features/1", json=body)
    assert response.status_code == 409 and "changed" in response.json()["detail"]
    complete = {"buildings_complete": True, "survey_id": stale}
    assert surveyed.client.put("/site/survey", json=complete).status_code == 409
    (tree,) = surveyed.client.get("/site/features").json()["features"]
    assert tree["properties"]["decision"] is None


def test_decisions_belong_to_the_survey_they_were_made_on(surveyed: Surveyed) -> None:
    """A new survey may number different things the same: nothing carries over."""
    write_survey(surveyed.survey, "shed")
    decide(surveyed, "1", {"decision": "building"})
    write_survey(surveyed.survey, "tree")
    (tree,) = surveyed.client.get("/site/features").json()["features"]
    assert tree["properties"]["decision"] is None


def test_a_design_keeps_clear_of_what_was_confirmed(surveyed: Surveyed) -> None:
    write_survey(surveyed.survey, "shed", "tree", "car")
    decide(surveyed, "1", {"decision": "building"})
    decide(surveyed, "2", {"decision": "keep_clear"})
    decide(surveyed, "3", {"decision": "ignore"})
    complete = list_complete(surveyed)
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
    decide(surveyed, "1", {"decision": "building"})
    job = surveyed.queue()
    surveyed.worker.run_next()
    (attempt,) = surveyed.client.get(f"/designs/{job}").json()["attempts"]
    assert "building_separation: unknown" in attempt["feedback"]


def test_the_list_cannot_be_complete_while_a_possible_building_is_undecided(
    surveyed: Surveyed,
) -> None:
    write_survey(surveyed.survey, "tree", "shed")
    decide(surveyed, "1", {"decision": "keep_clear"})
    refused = list_complete(surveyed)
    assert refused.status_code == 409 and "2" in refused.json()["detail"]
    decide(surveyed, "2", {"decision": "ignore"})
    accepted = list_complete(surveyed)
    assert accepted.status_code == 200
    assert surveyed.client.get("/site/features").json()["buildings_complete"] is True


def test_a_new_survey_is_not_confirmed_complete(surveyed: Surveyed) -> None:
    write_survey(surveyed.survey, "tree", status="agrees")  # no possible building to decide
    assert list_complete(surveyed).status_code == 200
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


def test_decisions_kept_in_a_file_make_the_same_site(tmp_path: Path) -> None:
    """The benchmark's surveyed site: a survey and the decisions about it, with who
    made them, applied exactly as the API applies the owner's."""
    write_survey(tmp_path / "survey.geojson", "shed", "tree")
    (tmp_path / "decisions.json").write_text(
        json.dumps(
            {
                "survey": "survey.geojson",
                "survey_id": survey_id(tmp_path / "survey.geojson"),
                "decided_by": "the team",
                "decisions": {"1": "building", "2": "keep_clear"},
                "buildings_complete": True,
            }
        ),
        encoding="utf-8",
    )
    kept = SiteDecisions.read(tmp_path / "decisions.json")
    assert kept.decided_by == "the team"
    site = kept.apply(synthetic_site())
    assert site.context.buildings_confirmed
    (building,) = site.context.confirmed_buildings
    assert building[0] == (30.0, 12.0)


@pytest.mark.parametrize(
    ("decisions", "complete", "match"),
    [
        ({"1": "building", "9": "ignore"}, False, "no feature 9"),
        ({"2": "keep_clear"}, True, "decide what these are first: 1"),
        ({"1": "building", "2": "keep_clear"}, "false", "true or false"),
    ],
)
def test_kept_decisions_are_checked_like_the_owners(
    tmp_path: Path, decisions: dict[str, str], complete: object, match: str
) -> None:
    write_survey(tmp_path / "survey.geojson", "shed", "tree")
    body = {
        "survey": "survey.geojson",
        "survey_id": survey_id(tmp_path / "survey.geojson"),
        "decided_by": "t",
        "decisions": decisions,
    }
    (tmp_path / "decisions.json").write_text(
        json.dumps(body | {"buildings_complete": complete}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=match):
        SiteDecisions.read(tmp_path / "decisions.json")


def survey_id(path: Path) -> str:
    survey = Survey.read(path)
    assert survey is not None
    return survey.id


def test_kept_decisions_belong_to_the_survey_they_were_made_on(tmp_path: Path) -> None:
    """A new survey may number different things the same: as in the API, old
    decisions mustn't land on them."""
    write_survey(tmp_path / "survey.geojson", "shed", "tree")
    body = {
        "survey": "survey.geojson",
        "survey_id": survey_id(tmp_path / "survey.geojson"),
        "decided_by": "t",
        "decisions": {"1": "building", "2": "keep_clear"},
        "buildings_complete": True,
    }
    (tmp_path / "decisions.json").write_text(json.dumps(body), encoding="utf-8")
    write_survey(tmp_path / "survey.geojson", "tree", "shed")  # surveyed again
    with pytest.raises(ValueError, match="decide again"):
        SiteDecisions.read(tmp_path / "decisions.json")


def test_the_demo_sites_kept_decisions_cover_its_survey() -> None:
    kept = SiteDecisions.read(Path("data/demo-site/decisions.json"))
    assert "pending the owner's confirmation" in kept.decided_by
    assert len(kept.decisions) == len(kept.survey.collection["features"]) == 5


def test_kept_decisions_about_another_site_are_refused(tmp_path: Path) -> None:
    """A survey of somewhere else, decided on: its features touch none of this title."""
    elsewhere = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "1",
                "properties": {"concept": "shed", "status": "agrees"},
                "geometry": square(5000.0, 5000.0, 6.0),
            }
        ],
    }
    (tmp_path / "survey.geojson").write_text(json.dumps(elsewhere), encoding="utf-8")
    body = {
        "survey": "survey.geojson",
        "survey_id": survey_id(tmp_path / "survey.geojson"),
        "decided_by": "t",
        "decisions": {"1": "building"},
        "buildings_complete": True,
    }
    (tmp_path / "decisions.json").write_text(json.dumps(body), encoding="utf-8")
    kept = SiteDecisions.read(tmp_path / "decisions.json")
    with pytest.raises(ValueError, match="not on this site's title"):
        kept.apply(synthetic_site())


def test_each_design_records_the_survey_and_decisions_it_was_checked_against(
    tmp_path: Path,
) -> None:
    surveyed = Surveyed(tmp_path)
    write_survey(surveyed.survey, "shed", "tree")
    decide(surveyed, "1", {"decision": "building"})
    job_id = surveyed.queue()
    assert surveyed.worker.run_next()
    decide(surveyed, "1", {"decision": "ignore"})  # after the design ran
    used = json.loads((tmp_path / "runs" / job_id / "survey.json").read_text())
    survey = Survey.read(surveyed.survey)
    assert survey is not None
    assert used == {
        "survey_id": survey.id,
        "decisions": {"1": "building"},
        "suggested": [],
        "buildings_complete": False,
        "buildings": [square(30.0, 12.0, 6.0)],  # its geometry kept, as decided then
    }


def test_a_design_on_a_site_without_a_survey_records_that(tmp_path: Path) -> None:
    surveyed = Surveyed(tmp_path)  # no survey file written
    job_id = surveyed.queue()
    assert surveyed.worker.run_next()
    used = json.loads((tmp_path / "runs" / job_id / "survey.json").read_text())
    assert used == {
        "survey_id": None,
        "decisions": {},
        "suggested": [],
        "buildings_complete": False,
        "buildings": [],
    }


def test_what_the_survey_is_sure_of_is_served_as_suggested_until_the_owner_decides(
    surveyed: Surveyed,
) -> None:
    # The demo site's title is far from these test squares: mostly the
    # neighbour's, so each is suggested Ignore.
    write_survey(surveyed.survey, "shed", "tree", status="agrees")
    body = surveyed.client.get("/site/features").json()
    props = [f["properties"] for f in body["features"]]
    assert [(p["decision"], p["suggested"]) for p in props] == [("ignore", True)] * 2
    decide(surveyed, "1", {"decision": "building"})
    props = [f["properties"] for f in surveyed.client.get("/site/features").json()["features"]]
    assert [(p["decision"], p["suggested"]) for p in props] == [
        ("building", False),
        ("ignore", True),
    ]


def test_a_design_uses_the_suggestions_and_records_which_they_were(tmp_path: Path) -> None:
    surveyed = Surveyed(tmp_path)
    write_survey(surveyed.survey, "shed", "tree", status="agrees")
    decide(surveyed, "1", {"decision": "building"})
    job_id = surveyed.queue()
    assert surveyed.worker.run_next()
    used = json.loads((tmp_path / "runs" / job_id / "survey.json").read_text())
    assert used["decisions"]["1"] == "building"  # the owner's own
    assert used["suggested"] == ["2"] and used["decisions"]["2"] in ("keep_clear", "ignore")
