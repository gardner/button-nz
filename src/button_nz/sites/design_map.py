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
    walls, outline, _ = _measured(attempt, site)
    return walls, outline


def _measured(attempt: Path, site: DemoSite) -> tuple[Polygon, Polygon, dict[str, float]]:
    """Walls, outline, and the Dwelling's lowest and highest points above the
    scene's datum (``base_m``, ``height_m``): the site's terrain tiles count
    from the same datum, so it stands in place on them."""
    raw = json.loads((attempt / "measurements.json").read_text(encoding="utf-8"))
    measured = parse_measurements(raw)
    if measured.footprint is None:
        raise ValueError(f"{attempt} has no measured footprint")
    frame = LocalFrame.centred_on(site.extent_nztm)
    walls = Polygon([frame.to_nztm(p) for p in measured.footprint])
    plan: Ring = measured.outline or measured.footprint
    heights: dict[str, float] = {}
    if measured.z_min is not None and measured.z_max is not None:
        heights = {"base_m": round(measured.z_min, 2), "height_m": round(measured.z_max, 2)}
    return walls, Polygon([frame.to_nztm(p) for p in plan]), heights


def design_layers(attempt: Path, site: DemoSite, survey: Path | None) -> dict[str, Any]:
    """The layers of the accepted ``attempt`` of a design on ``site``, whose
    survey is ``survey``; the design's run folder holds what it was checked against."""
    walls, outline, heights = _measured(attempt, site)
    parcels = [Polygon(p.ring) for p in site.parcels]
    title = union_all(parcels)
    internal = union_all([p.boundary for p in parcels]).difference(title.boundary.buffer(1e-6))
    buildings = _confirmed(attempt.parent / SURVEY_USED, survey)
    targets = {
        "title_boundary_setback": title.boundary,
        "section_boundary_setback": internal,
        "building_separation": Polygon() if buildings is None else buildings,
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
        "walls": collection([(walls, heights)]),
        "outline": collection([(outline, heights)]),
        "distances": collection(lines),
        # a check whose line can't be drawn now, and why: never left out silently
        "unknown": []
        if buildings is not None
        else [{"check": "building_separation", "reason": "the survey has changed since it ran"}],
    }


def _confirmed(record: Path, survey: Path | None) -> BaseGeometry | None:
    """The buildings the design was checked against, as its record kept them;
    None if that can't be known (an older record, made on a survey since replaced)."""
    if not record.is_file():
        return Polygon()
    used = json.loads(record.read_text(encoding="utf-8"))
    if "buildings" in used:
        kept = [shape(g) for g in used["buildings"]]
    else:  # records before the geometry was kept: only the same survey can say
        found = None if survey is None else Survey.read(survey)
        if found is None or used.get("survey_id") != found.id:
            return None
        decided: dict[str, str] = used.get("decisions", {})
        kept = [
            shape(f["geometry"])
            for f in found.collection["features"]
            if decided.get(str(f["id"])) == "building"
        ]
    return union_all(kept) if kept else Polygon()


def _line(outline: BaseGeometry, target: BaseGeometry) -> BaseGeometry:
    near, far = nearest_points(outline, target)
    return LineString([near, far])
