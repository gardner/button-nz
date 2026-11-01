"""A person's decisions about surveyed site features, and the site they make.

The survey only suggests what is there; nothing it finds constrains a design
until someone confirms it. Each decision is made on one survey (identified by
a hash of its file), so a new survey, which may number different things the
same, starts undecided.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from shapely import MultiPolygon, Polygon, union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from button_nz.agent.site import DesignSite
from button_nz.geo.geometry import Ring
from button_nz.perception.features import GROUND, STRUCTURES, VEGETATION, Status


class Decision(StrEnum):
    BUILDING = "building"  # an existing building: a new one keeps its distance
    KEEP_CLEAR = "keep_clear"  # e.g. a tree or garden bed: nothing is built on it
    IGNORE = "ignore"  # e.g. a parked car, or not really there


@dataclass(frozen=True)
class Survey:
    id: str
    collection: dict[str, Any]  # an NZTM GeoJSON FeatureCollection

    @classmethod
    def read(cls, path: Path) -> Survey | None:
        """The survey at ``path``, or None if there isn't one yet."""
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        return cls(hashlib.sha256(raw).hexdigest()[:16], json.loads(raw))

    def feature(self, feature_id: str) -> dict[str, Any] | None:
        features: list[dict[str, Any]] = self.collection["features"]
        return next((f for f in features if f["id"] == feature_id), None)


def undecided_buildings(survey: Survey, decisions: Mapping[str, str]) -> list[str]:
    """Features that might be buildings and have no decision yet: a structure,
    anything the LiDAR disagrees with, and raised ground nothing labelled."""
    doubtful = {Status.CONFLICT.value, Status.UNLABELLED.value}
    return [
        f["id"]
        for f in survey.collection["features"]
        if f["id"] not in decisions
        and (f["properties"]["concept"] in STRUCTURES or f["properties"]["status"] in doubtful)
    ]


MIN_ON_TITLE = 0.25  # less of a feature than this on the title: the neighbour's


def suggested(survey: Survey, title: BaseGeometry) -> dict[str, Decision]:
    """The decision each feature starts with, from what the survey measured,
    for the owner to change: mostly the neighbour's, a parked car or open
    ground is ignored, a building the LiDAR agrees with is a building, and
    vegetation is kept clear. What the LiDAR disputes, or raised ground nothing
    labelled, has none: the owner is asked, not guessed for."""
    found: dict[str, Decision] = {}
    for feature in survey.collection["features"]:
        decision = _suggestion(feature, title)
        if decision is not None:
            found[feature["id"]] = decision
    return found


def _suggestion(feature: dict[str, Any], title: BaseGeometry) -> Decision | None:
    concept, status = feature["properties"]["concept"], feature["properties"]["status"]
    if status in (Status.CONFLICT, Status.UNLABELLED):
        return None
    area = shape(feature["geometry"])
    if area.area > 0 and area.intersection(title).area / area.area < MIN_ON_TITLE:
        return Decision.IGNORE
    if status == Status.TRANSIENT or concept in GROUND:
        return Decision.IGNORE
    if concept in STRUCTURES and status == Status.AGREES:
        return Decision.BUILDING
    if concept in VEGETATION:
        return Decision.KEEP_CLEAR
    return None


def effective(
    survey: Survey, decisions: Mapping[str, str], title: BaseGeometry, fixed: bool = False
) -> dict[str, str]:
    """The decisions a design is checked on: the owner's, and for the rest
    what the survey suggests. A ``fixed`` survey has only the decisions made on
    it: a suggestion there would be credited to whoever fixed it, who could no
    longer change it (confirming the buildings list stores the suggestions as
    theirs, before it is fixed)."""
    if fixed:
        return dict(decisions)
    return {**{k: v.value for k, v in suggested(survey, title).items()}, **decisions}


def title_of(rings: Iterable[Ring]) -> BaseGeometry:
    """The land on a title, from its parcels' rings."""
    return union_all([Polygon(ring) for ring in rings])


def confirmed(
    site: DesignSite, survey: Survey, decisions: Mapping[str, Decision], complete: bool = False
) -> DesignSite:
    """``site`` with the buildings and keep-clear areas a person confirmed, and
    whether they said the buildings are ``complete``ly listed."""
    chosen: dict[Decision, list[Ring]] = {Decision.BUILDING: [], Decision.KEEP_CLEAR: []}
    for feature in survey.collection["features"]:
        decision = decisions.get(feature["id"])
        if decision is not None and decision in chosen:
            chosen[decision] += _rings(feature["geometry"])
    context = replace(
        site.context,
        confirmed_buildings=tuple(chosen[Decision.BUILDING]),
        preservation_areas=tuple(chosen[Decision.KEEP_CLEAR]),
        buildings_confirmed=complete,
    )
    return replace(site, context=context)


def _rings(geometry: dict[str, Any]) -> list[Ring]:
    """The outer ring of each polygon: a hole in a tree's canopy is still kept clear."""
    polygons = shape(geometry)
    parts = polygons.geoms if isinstance(polygons, MultiPolygon) else [polygons]
    return [
        tuple((float(x), float(y)) for x, y, *_ in part.exterior.coords)
        for part in parts
        if isinstance(part, Polygon)
    ]


@dataclass(frozen=True)
class SiteDecisions:
    """A survey and decisions about it kept in a file (``decisions.json`` beside
    it), with who made them: the benchmark's surveyed site. They are checked as
    the API checks the owner's, and applied the same way."""

    survey: Survey
    decisions: dict[str, Decision]
    complete: bool
    decided_by: str

    @classmethod
    def read(cls, path: Path) -> SiteDecisions:
        kept = json.loads(path.read_text(encoding="utf-8"))
        survey = Survey.read(path.parent / kept["survey"])
        if survey is None:
            raise ValueError(f"{path} names a survey that isn't there: {kept['survey']}")
        if survey.id != kept["survey_id"]:  # a new survey may number other things the same
            raise ValueError(
                f"{path} was decided on survey {kept['survey_id']}, not {survey.id}: decide again"
            )
        decisions = {k: Decision(v) for k, v in kept["decisions"].items()}
        unknown = [k for k in decisions if survey.feature(k) is None]
        if unknown:
            raise ValueError(f"{path} decides about no feature {', '.join(unknown)}")
        complete = kept["buildings_complete"]
        if not isinstance(complete, bool):  # "false" would read as true
            raise ValueError(f"{path}: buildings_complete must be true or false")
        undecided = undecided_buildings(survey, decisions)
        if complete and undecided:
            raise ValueError(f"{path}: decide what these are first: {', '.join(undecided)}")
        return cls(survey, decisions, complete, str(kept["decided_by"]))

    def apply(self, site: DesignSite) -> DesignSite:
        """``site`` with these decisions, which must be about things on its title:
        a survey of somewhere else would silently constrain nothing."""
        title = union_all([Polygon(ring) for ring in site.context.parcels])
        elsewhere = [k for k in self.decisions if not shape(self._geometry(k)).intersects(title)]
        if elsewhere:
            raise ValueError(f"features {', '.join(elsewhere)} are not on this site's title")
        return confirmed(site, self.survey, self.decisions, self.complete)

    def _geometry(self, feature_id: str) -> dict[str, Any]:
        feature = self.survey.feature(feature_id)
        assert feature is not None  # read() refuses decisions about unknown features
        return feature["geometry"]
