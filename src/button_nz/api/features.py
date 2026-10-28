"""The surveyed site features, and a person's decisions about them, over HTTP.

    GET  /site/features                                the survey, with each decision
    PUT  /site/features/{id} {decision, survey_id}     building, keep_clear or ignore
    PUT  /site/survey {buildings_complete, survey_id}  every building is listed

The survey is read from its file on each request, so a new survey (written by
``python -m button_nz.perception.survey``) is served without a restart, and
starts undecided. A decision names the survey it was made on: one made on an
older survey is refused (409), since its feature ids may mean other things now.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from button_nz.api.store import Store
from button_nz.perception.confirm import Decision, Survey, undecided_buildings


class DecisionRequest(BaseModel):
    decision: Decision
    survey_id: str


class SurveyRequest(BaseModel):
    buildings_complete: bool
    survey_id: str


def features_router(store: Store, survey: Path | None) -> APIRouter:
    router = APIRouter()

    @router.get("/site/features")
    def get_features() -> dict[str, Any]:
        found = _survey(survey)
        decisions = store.decisions(found.id)
        return {
            **found.collection,
            "survey_id": found.id,
            "buildings_complete": store.buildings_complete(found.id),
            "features": [_decided(f, decisions.get(f["id"])) for f in found.collection["features"]],
        }

    @router.put("/site/features/{feature_id}")
    def put_feature(feature_id: str, request: DecisionRequest) -> dict[str, Any]:
        found = _survey(survey, request.survey_id)
        feature = found.feature(feature_id)
        if feature is None:
            raise HTTPException(404, f"no feature {feature_id} in survey {found.id}")
        store.decide(found.id, feature_id, request.decision)
        return _decided(feature, request.decision)

    @router.put("/site/survey")
    def put_survey(request: SurveyRequest) -> dict[str, Any]:
        found = _survey(survey, request.survey_id)
        undecided = undecided_buildings(found, store.decisions(found.id))
        if request.buildings_complete and undecided:
            raise HTTPException(409, f"decide what these are first: {', '.join(undecided)}")
        store.set_buildings_complete(found.id, request.buildings_complete)
        return {"survey_id": found.id, "buildings_complete": request.buildings_complete}

    return router


def _survey(path: Path | None, decided_on: str | None = None) -> Survey:
    """The survey being served; if a decision ``decided_on`` another, a 409."""
    found = None if path is None else Survey.read(path)
    if found is None:
        raise HTTPException(404, "no survey yet: run python -m button_nz.perception.survey")
    if decided_on is not None and decided_on != found.id:
        raise HTTPException(409, "the survey has changed since this page loaded: reload it")
    return found


def _decided(feature: dict[str, Any], decision: str | None) -> dict[str, Any]:
    return {**feature, "properties": {**feature["properties"], "decision": decision}}
