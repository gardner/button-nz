"""The surveyed site features, and a person's decisions about them, over HTTP.

    GET  /site/features                                the survey, with each decision
    PUT  /site/features/{id} {decision, survey_id}     building, keep_clear or ignore
    PUT  /site/survey {buildings_complete, survey_id}  every building is listed

The same, for any site, under ``/sites/{site_id}`` (``site_features_router``);
``/site`` is the demo site.

A public server can fix the survey as someone decided it (``FixedSurvey``):
it is served with who that was, and changes to it are refused (403). It is
pinned to the survey they decided: a survey file replaced since is refused
(409) rather than served undecided (``api/fixed.py``).

The survey is read from its file on each request, so a new survey (written by
``python -m button_nz.perception.survey``) is served without a restart, and
starts undecided. A decision names the survey it was made on: one made on an
older survey is refused (409), since its feature ids may mean other things now.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from shapely.geometry.base import BaseGeometry

from button_nz.api.fixed import FixedSurvey, SurveyReplaced, read_fixed
from button_nz.api.store import Store
from button_nz.perception.confirm import Decision, Survey, effective, undecided_buildings


class DecisionRequest(BaseModel):
    decision: Decision
    survey_id: str


class SurveyRequest(BaseModel):
    buildings_complete: bool
    survey_id: str


type Resolve = Callable[[str], tuple[Path | None, FixedSurvey | None, BaseGeometry]]
"""A site id to its survey file, how it is fixed (None: open to decisions),
and the land on its title (what a feature's suggested decision weighs)."""


def features_router(
    store: Store, survey: Path | None, title: BaseGeometry, fixed: FixedSurvey | None = None
) -> APIRouter:
    """The demo site's survey, at ``/site``."""
    return _router(store, "/site", lambda _: (survey, fixed, title))


def site_features_router(store: Store, resolve: Resolve) -> APIRouter:
    """Any site's survey, at ``/sites/{site_id}``."""
    return _router(store, "/sites/{site_id}", resolve)


def _router(store: Store, prefix: str, resolve: Resolve) -> APIRouter:
    router = APIRouter()

    def resolved(site_id: str) -> tuple[Survey | None, str | None, BaseGeometry]:
        """The site's survey, read once and checked to be the fixed survey if
        it is fixed (else a 409), who fixed it, and the land on its title."""
        path, fixed, title = resolve(site_id)
        try:
            survey = read_fixed(path, fixed)
        except SurveyReplaced as error:
            raise HTTPException(409, str(error)) from None
        return survey, None if fixed is None else fixed.decided_by, title

    def unless_fixed(decided_by: str | None) -> None:
        if decided_by is not None:
            raise HTTPException(403, f"This server's survey is fixed, as {decided_by} decided it.")

    @router.get(f"{prefix}/features")
    def get_features(site_id: str = "") -> dict[str, Any]:
        survey, decided_by, title = resolved(site_id)
        found = _survey(survey)
        own = store.decisions(found.id)
        decisions = effective(found, own, title)
        return {
            **found.collection,
            "survey_id": found.id,
            "buildings_complete": store.buildings_complete(found.id),
            "fixed": decided_by is not None,
            "decided_by": decided_by,
            "features": [
                _decided(f, decisions.get(f["id"]), suggested=f["id"] not in own)
                for f in found.collection["features"]
            ],
        }

    @router.put(f"{prefix}/features/{{feature_id}}")
    def put_feature(feature_id: str, request: DecisionRequest, site_id: str = "") -> dict[str, Any]:
        survey, decided_by, _ = resolved(site_id)
        unless_fixed(decided_by)
        found = _survey(survey, request.survey_id)
        feature = found.feature(feature_id)
        if feature is None:
            raise HTTPException(404, f"no feature {feature_id} in survey {found.id}")
        store.decide(found.id, feature_id, request.decision)
        return _decided(feature, request.decision)

    @router.put(f"{prefix}/survey")
    def put_survey(request: SurveyRequest, site_id: str = "") -> dict[str, Any]:
        survey, decided_by, title = resolved(site_id)
        unless_fixed(decided_by)
        found = _survey(survey, request.survey_id)
        undecided = undecided_buildings(found, effective(found, store.decisions(found.id), title))
        if request.buildings_complete and undecided:
            raise HTTPException(409, f"decide what these are first: {', '.join(undecided)}")
        store.set_buildings_complete(found.id, request.buildings_complete)
        return {"survey_id": found.id, "buildings_complete": request.buildings_complete}

    return router


def _survey(found: Survey | None, decided_on: str | None = None) -> Survey:
    """The survey being served; if a decision ``decided_on`` another, a 409."""
    if found is None:
        raise HTTPException(404, "no survey yet: run python -m button_nz.perception.survey")
    if decided_on is not None and decided_on != found.id:
        raise HTTPException(409, "the survey has changed since this page loaded: reload it")
    return found


def _decided(
    feature: dict[str, Any], decision: str | None, suggested: bool = False
) -> dict[str, Any]:
    """The feature with its decision, and whether the survey suggested it
    (the owner hasn't decided it themselves)."""
    marked = {"decision": decision, "suggested": suggested and decision is not None}
    return {**feature, "properties": {**feature["properties"], **marked}}
