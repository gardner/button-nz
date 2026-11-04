"""Observations the design model can request: LiDAR views and measurements of
the site, in the model's local frame, with the parcels outlined (plan §7).

They re-present the measured terrain and add no information. A bad request
(unknown tool, missing or malformed argument) is an ``ObservationError``:
feedback for the model, not a crash.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from shapely import Polygon

from button_nz.agent.conversation import Observe
from button_nz.agent.room import largest_rectangles, longest_edge_angle, room_of
from button_nz.agent.site import DesignSite
from button_nz.evaluation import ground_range
from button_nz.geo.geometry import Point, Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.lidar import (
    View,
    contours,
    cross_section,
    hillshade,
    inspect_elevation,
    ndsm_map,
    normal_map,
    overlay,
    slope_map,
)
from button_nz.lidar.analysis import NoCellsInside

_EPS = 1e-9
SCALE = 8  # pixels per metre cell
PROFILE_SAMPLES = 41  # at most this many cross-section heights in the text
HEIGHTS = ("min_m", "max_m", "mean_m")  # NZVD2016 in the views' facts; shown as script z


class ObservationError(ValueError):
    """The model's observation request could not be carried out."""


@dataclass(frozen=True)
class Observation:
    text: str
    png: bytes | None


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
OBSERVATION_TOOLS: list[dict[str, Any]] = [
    _tool(
        "render_hillshade",
        "Shaded relief of the ground: shows banks, ridges and hollows.",
        {"azimuth_deg": {"type": "number"}, "altitude_deg": {"type": "number"}},
        [],
    ),
    _tool(
        "render_contours",
        "Elevation contours.",
        {"interval_m": {"type": "number", "exclusiveMinimum": 0}},
        [],
    ),
    _tool(
        "render_height_map",
        "Heatmap of ground slope, height above ground (structures/vegetation), or surface normals.",
        {"mode": {"type": "string", "enum": ["slope", "above_ground", "normals"]}},
        ["mode"],
    ),
    _tool(
        "render_cross_section",
        "Terrain profile along a line between two local (x, y) points.",
        {"start": _POINT, "end": _POINT},
        ["start", "end"],
    ),
    _tool(
        "inspect_elevation",
        "Ground height, relief and slope statistics inside a local polygon.",
        {"polygon": {"type": "array", "items": _POINT, "minItems": 3}},
        ["polygon"],
    ),
]


def standard_views(site: DesignSite) -> tuple[tuple[Observe, Observation], ...]:
    """The views every design starts with, each as the model asking for it
    would get it: the ground's shape (hillshade, contours), what stands on it
    (height above ground), and a profile the length of the room's largest
    rectangle, where a dwelling can go (none if no rectangle fits). They are
    deterministic and take about 0.1 s, so they are made per run: the room
    changes with the owner's decisions."""
    requests = [
        Observe("render_hillshade", {}),
        Observe("render_contours", {"interval_m": 0.25}),
        Observe("render_height_map", {"mode": "above_ground"}),
    ]
    context = site.context
    room = room_of(context.parcels, context.confirmed_buildings, context.preservation_areas)
    found = largest_rectangles(room, longest_edge_angle(context.parcels), count=1)
    if found:
        start, end = (list(site.frame.to_local(p)) for p in _long_axis(found[0].polygon))
        requests.append(Observe("render_cross_section", {"start": start, "end": end}))
    return tuple((request, observe(site, request)) for request in requests)


def _long_axis(rectangle: Polygon) -> tuple[Point, Point]:
    """The midpoints of ``rectangle``'s two short sides."""
    a, b, c, d = ((float(x), float(y)) for x, y in list(rectangle.exterior.coords)[:4])
    if math.dist(a, b) > math.dist(b, c):  # a-b is a long side: b-c and d-a are short
        a, b, c, d = b, c, d, a
    return _midpoint(a, b), _midpoint(c, d)


def _midpoint(p: Point, q: Point) -> Point:
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)


def observe(site: DesignSite, request: Observe) -> Observation:
    try:
        return _observe(site, request.tool, request.arguments)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ObservationError):
            raise
        raise ObservationError(f"{request.tool}: bad arguments ({error!r})") from error


def _observe(site: DesignSite, tool: str, args: Mapping[str, Any]) -> Observation:
    grid = site.context.terrain
    if tool == "render_hillshade":
        view = hillshade(
            grid, float(args.get("azimuth_deg", 315)), float(args.get("altitude_deg", 45)), SCALE
        )
    elif tool == "render_contours":
        interval = float(args.get("interval_m", 0.25))
        view = replace(contours(grid, interval, SCALE), notes=f"Contours every {interval:g} m.")
    elif tool == "render_height_map":
        modes = {"slope": slope_map, "above_ground": ndsm_map, "normals": normal_map}
        if args["mode"] not in modes:
            raise ObservationError(f"render_height_map: mode must be one of {sorted(modes)}")
        view = modes[args["mode"]](grid, SCALE)
    elif tool == "render_cross_section":
        return _described(site, _cross_section(site, args["start"], args["end"]), outlined=False)
    elif tool == "inspect_elevation":
        polygon = tuple(_local(site, point) for point in args["polygon"])
        return Observation(_facts(site, "Inside the polygon:", _elevation(grid, polygon)), None)
    else:
        raise ObservationError(f"unknown observation tool {tool!r}")
    outlined = overlay(view, grid, site.context.parcels, SCALE)
    return _described(site, outlined, outlined=True)


def _elevation(grid: TerrainGrid, polygon: Ring) -> dict[str, float]:
    """The ground range exactly as the floor_level check measures it, plus the
    slope statistics of the cells inside, if any cell centre is."""
    low, high = ground_range(Polygon(polygon), grid)
    try:
        stats = inspect_elevation(grid, polygon)
    except NoCellsInside:  # narrower than a cell: no centre inside to average
        stats = {}
    return stats | {"min_m": low, "max_m": high, "relief_m": high - low}


def _cross_section(site: DesignSite, start: Sequence[float], end: Sequence[float]) -> View:
    """The profile, described in the local coordinates the model asked in."""
    datum = site.scene["frame"]["datum_m"]
    section = cross_section(
        site.context.terrain, _local(site, start), _local(site, end), datum_m=datum
    )
    samples = range(len(section.heights))
    if len(samples) > PROFILE_SAMPLES:  # evenly spaced, ends included
        last = len(samples) - 1
        samples = sorted({round(i * last / (PROFILE_SAMPLES - 1)) for i in range(PROFILE_SAMPLES)})
    profile = ", ".join(
        f"{section.distances[i]:.1f} m: {section.heights[i] - datum:.2f}" for i in samples
    )
    notes = (
        f"Terrain profile from {_label(start)} to {_label(end)} (local metres). "
        f"Ground z along it (distance: z): {profile}."
    )
    return replace(section.view, notes=notes)


def _label(point: Sequence[float]) -> str:
    return f"({float(point[0]):.1f}, {float(point[1]):.1f})"


def _local(site: DesignSite, point: Sequence[float]) -> Point:
    """A local point on the measured terrain, in NZTM; off it is feedback in local terms."""
    if len(point) != 2:
        raise ObservationError(f"a point must be [x, y], not {list(point)}")
    x, y = float(point[0]), float(point[1])
    west, south, east, north = _extent(site)
    if not (west - _EPS <= x <= east + _EPS and south - _EPS <= y <= north + _EPS):
        raise ObservationError(
            f"{_label(point)} is outside the terrain, which spans "
            f"x {west:g}..{east:g}, y {south:g}..{north:g} (local metres)"
        )
    return site.frame.to_nztm((x, y))


def _extent(site: DesignSite) -> tuple[float, float, float, float]:
    """The terrain's cell centres, local: the ground is measured only there."""
    grid, half = site.context.terrain, site.context.terrain.cell_m / 2
    west, south = site.frame.to_local((grid.bbox[0] + half, grid.bbox[1] + half))
    east, north = site.frame.to_local((grid.bbox[2] - half, grid.bbox[3] - half))
    return round(west, 6), round(south, 6), round(east, 6), round(north, 6)


def _described(site: DesignSite, view: View, outlined: bool) -> Observation:
    notes = view.notes
    if outlined:
        notes += " Red outlines: the title's parcels. North is up; 1 cell = 1 m."
    return Observation(_facts(site, notes, view.facts), view.png)


def _facts(site: DesignSite, heading: str, facts: Mapping[str, float]) -> str:
    """The view's numbers, with ground heights as the z the model's script uses."""
    datum = site.scene["frame"]["datum_m"]
    if any(name in HEIGHTS for name in facts):
        heading += " Heights are metres above the scene datum: the z your script uses."
    lines = [
        heading,
        *(
            f"- {name}: {value - datum if name in HEIGHTS else value:.2f}"
            for name, value in facts.items()
        ),
    ]
    return "\n".join(lines)


__all__ = ["OBSERVATION_TOOLS", "Observation", "ObservationError", "observe", "standard_views"]
