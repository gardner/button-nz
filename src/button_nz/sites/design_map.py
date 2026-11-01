"""An accepted design on its site's map, as GeoJSON in EPSG:4326:

- ``walls``: the outside of its walls, as the trusted pass measured them;
- ``outline``: all it covers from above, eaves included (or the walls);
- ``distances``: the shortest line from the outline to what the evaluator
  measures it against, each with its check, metres and the 2 m required: the
  title boundary, the lines between the title's parcels, and the buildings the
  survey had confirmed when the design was checked.

The geometry is the evaluator's own: the outline, the title and its internal
lines as ``evaluation.checks`` makes them, so the map and the verdict agree.
"""

import json
from pathlib import Path
from typing import Any

from shapely import LineString, Polygon, union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from button_nz.agent.proposal import parse_measurements
from button_nz.api.jobs import SURVEY_USED
from button_nz.demo_site import DemoSite
from button_nz.evaluation.checks import MIN_SEPARATION_M
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.perception.confirm import Survey
from button_nz.sites.layers import collection


def walls_and_outline(attempt: Path, site: DemoSite) -> tuple[Polygon, Polygon]:
    """The attempt's walls and outline, in NZTM: measured in the site's frame,
    centred on its parcels as every design scene is."""
    raw = json.loads((attempt / "measurements.json").read_text(encoding="utf-8"))
    measured = parse_measurements(raw)
    if measured.footprint is None:
        raise ValueError(f"{attempt} has no measured footprint")
    frame = LocalFrame.centred_on(site.extent_nztm)
    walls = Polygon([frame.to_nztm(p) for p in measured.footprint])
    plan: Ring = measured.outline or measured.footprint
    return walls, Polygon([frame.to_nztm(p) for p in plan])


def design_layers(attempt: Path, site: DemoSite, survey: Path | None) -> dict[str, Any]:
    """The layers of the accepted ``attempt`` of a design on ``site``, whose
    survey is ``survey``; the design's run folder holds what it was checked against."""
    walls, outline = walls_and_outline(attempt, site)
    parcels = [Polygon(p.ring) for p in site.parcels]
    title = union_all(parcels)
    internal = union_all([p.boundary for p in parcels]).difference(title.boundary.buffer(1e-6))
    targets = {
        "title_boundary_setback": title.boundary,
        "section_boundary_setback": internal,
        "building_separation": _confirmed(attempt.parent / SURVEY_USED, survey),
    }
    lines = [
        (
            _line(outline, target),
            {
                "check": name,
                "metres": round(outline.distance(target), 3),
                "required": MIN_SEPARATION_M,
            },
        )
        for name, target in targets.items()
        if not target.is_empty
    ]
    return {
        "walls": collection([(walls, {})]),
        "outline": collection([(outline, {})]),
        "distances": collection(lines),
    }


def _confirmed(record: Path, survey: Path | None) -> BaseGeometry:
    """The buildings the design was checked against: the survey's features its
    record says were confirmed as buildings."""
    found = None if survey is None else Survey.read(survey)
    if found is None or not record.is_file():
        return Polygon()
    used = json.loads(record.read_text(encoding="utf-8"))
    if used.get("survey_id") != found.id:
        return Polygon()  # checked against an earlier survey: its buildings aren't these
    decided: dict[str, str] = used.get("decisions", {})
    buildings = [
        shape(f["geometry"])
        for f in found.collection["features"]
        if decided.get(str(f["id"])) == "building"
    ]
    return union_all(buildings) if buildings else Polygon()


def _line(outline: BaseGeometry, target: BaseGeometry) -> BaseGeometry:
    near, far = nearest_points(outline, target)
    return LineString([near, far])
