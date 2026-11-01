"""Tests for button_nz.perception.confirm.suggested: the decision a survey
feature starts with, which the owner can always change."""

from typing import Any

from shapely import Polygon

from button_nz.perception.confirm import Decision, Survey, effective, suggested

TITLE = Polygon([(0, 0), (40, 0), (40, 30), (0, 30)])


def feature(fid: str, concept: str, status: str, x: float, size: float = 6.0) -> dict[str, Any]:
    ring = [[x, 10.0], [x + size, 10.0], [x + size, 10.0 + size], [x, 10.0 + size], [x, 10.0]]
    return {
        "type": "Feature",
        "id": fid,
        "properties": {"concept": concept, "status": status},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def survey(*features: dict[str, Any]) -> Survey:
    return Survey("s1", {"type": "FeatureCollection", "features": list(features)})


def test_what_the_survey_is_sure_of_starts_decided() -> None:
    found = survey(
        feature("1", "shed", "agrees", 5),
        feature("2", "tree", "agrees", 15),
        feature("3", "tree", "unchecked", 25),
        feature("4", "vehicle", "transient", 30),
        feature("5", "driveway", "unchecked", 2, 3),
    )
    assert suggested(found, TITLE) == {
        "1": Decision.BUILDING,
        "2": Decision.KEEP_CLEAR,
        "3": Decision.KEEP_CLEAR,
        "4": Decision.IGNORE,
        "5": Decision.IGNORE,
    }


def test_what_the_lidar_disputes_is_left_for_the_owner() -> None:
    found = survey(
        feature("1", "shed", "conflict", 5), feature("2", "unlabelled", "unlabelled", 15)
    )
    assert suggested(found, TITLE) == {}


def test_a_feature_mostly_on_the_neighbours_land_is_ignored() -> None:
    mostly_out = feature("1", "tree", "agrees", 38, 10)  # 2 of its 10 m across on the title
    half_in = feature("2", "tree", "agrees", 35, 10)  # half on the title: the owner's to keep
    assert suggested(survey(mostly_out, half_in), TITLE) == {
        "1": Decision.IGNORE,
        "2": Decision.KEEP_CLEAR,
    }


def test_the_owners_own_decision_wins() -> None:
    found = survey(feature("1", "tree", "agrees", 5), feature("2", "shed", "conflict", 15))
    assert effective(found, {"1": "ignore"}, TITLE) == {"1": "ignore"}
    assert effective(found, {}, TITLE) == {"1": "keep_clear"}
