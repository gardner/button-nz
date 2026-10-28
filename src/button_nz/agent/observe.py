"""Observations the design model can request: LiDAR views and measurements of
the site, in the model's local frame, with the parcels outlined (plan §7).

They re-present the measured terrain and add no information. A bad request
(unknown tool, missing or malformed argument) is an ``ObservationError``:
feedback for the model, not a crash.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from button_nz.agent.conversation import Observe
from button_nz.agent.site import DesignSite
from button_nz.geo.geometry import Point
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

SCALE = 8  # pixels per metre cell


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
    _tool("render_contours", "Elevation contours.", {"interval_m": {"type": "number"}}, []),
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
        view = contours(grid, float(args.get("interval_m", 0.25)), SCALE)
    elif tool == "render_height_map":
        modes = {"slope": slope_map, "above_ground": ndsm_map, "normals": normal_map}
        if args["mode"] not in modes:
            raise ObservationError(f"render_height_map: mode must be one of {sorted(modes)}")
        view = modes[args["mode"]](grid, SCALE)
    elif tool == "render_cross_section":
        start, end = _local(site, args["start"]), _local(site, args["end"])
        return _described(cross_section(grid, start, end).view, outlined=False)
    elif tool == "inspect_elevation":
        polygon = tuple(_local(site, point) for point in args["polygon"])
        stats = inspect_elevation(grid, polygon)
        return Observation(_facts("Inside the polygon:", stats), None)
    else:
        raise ObservationError(f"unknown observation tool {tool!r}")
    outlined = overlay(view, grid, site.context.parcels, SCALE)
    return _described(outlined, outlined=True)


def _local(site: DesignSite, point: Sequence[float]) -> Point:
    if len(point) != 2:
        raise ObservationError(f"a point must be [x, y], not {list(point)}")
    return site.frame.to_nztm((float(point[0]), float(point[1])))


def _described(view: View, outlined: bool) -> Observation:
    notes = view.notes
    if outlined:
        notes += " Red outlines: the title's parcels. North is up; 1 cell = 1 m."
    return Observation(_facts(notes, view.facts), view.png)


def _facts(heading: str, facts: Mapping[str, float]) -> str:
    lines = [heading, *(f"- {name}: {value:.2f}" for name, value in facts.items())]
    return "\n".join(lines)


__all__ = ["OBSERVATION_TOOLS", "Observation", "ObservationError", "observe"]
