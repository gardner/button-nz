"""Where a rectangular dwelling can stand on its site, solved before any script
is written: the placements that pass every siting check.

A plan of ``length_m`` x ``width_m`` walls, its outline grown by ``eaves_m``
all round, is tried at every ``ANGLE_STEP_DEG`` from the title's longest edge
and every ``GRID_M`` across ``room.py``'s room, with the lines between the
title's sections kept ``section_clear_m`` clear (2 m: they then pass, never
come back unknown). Two quick tests narrow the field: the outline lies in the
room, and the LiDAR cells under the walls span no more than the floor-level
rule allows (the evaluator's range also counts the outline's crossings, so it
is never less). Each placement returned is then confirmed by the evaluator's
own checks (``evaluation.checks``), so solver and evaluator agree by
construction, and carries the clearances those checks measured. The evaluator
is asked about the best ``MAX_CONFIRMED`` candidates at most, and a large
site's grid is coarser (``MAX_CANDIDATES``), which keeps a search under a
second: a placement can be missed, never invented.

Placements are ranked by a preference, not a rule: the margin (the least
clearance to a 2 m line: title boundary, section line, listed building),
counted up to ``TARGET_MARGIN_M``; then the least ground range under the
walls, to the ``GROUND_STEP_M`` (fewest earthworks); then the farthest from
the street edge. Those returned are distinct spots: any two share less than
half their walls.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

import numpy as np
import shapely
from numpy.typing import NDArray
from shapely import LineString, MultiPolygon, Polygon, union_all
from shapely.geometry.base import BaseGeometry

from button_nz.agent.room import buffer_at_least, longest_edge_angle, room_of
from button_nz.agent.site import DesignSite
from button_nz.evaluation import checks
from button_nz.evaluation.checks import MAX_FLOOR_ABOVE_GROUND_M, MIN_SEPARATION_M
from button_nz.evaluation.model import (
    Check,
    Footprint,
    InvalidProposal,
    Proposal,
    SiteContext,
    Status,
)
from button_nz.geo.geometry import Point
from button_nz.sites.frontages import Frontage

ANGLE_STEP_DEG = 15.0
GRID_M = 0.5
TARGET_MARGIN_M = 2.5  # a comfort margin past the 2 m rules: a preference, stated as one
GROUND_STEP_M = 0.1  # ground ranges this close rank as equal
MAX_CANDIDATES = 50_000  # poses tried at most, over every angle: a large site's grid is coarser
MAX_CONFIRMED = 500  # the evaluator is asked about this many at most: about 0.25 s
ROUNDING_M = 0.01  # the room is drawn in this far: a corner printed to the cm stays in it
PROMPT_EAVES_M = 0.6
# a bespoke design's plain plans, 66 to 70 m² outside the walls: long and narrow
# ones fit where a squarer one can't
PROMPT_PLANS = ((10.0, 7.0), (12.0, 5.5), (15.0, 4.5))
_EPS = 1e-9
_CLEARANCES = {  # the checks whose distance is a clearance, and its name
    "title_boundary_setback": "title_boundary_m",
    "section_boundary_setback": "section_line_m",
    "building_separation": "building_m",
}


@dataclass(frozen=True)
class Placement:
    walls: Polygon  # the site's frame (NZTM)
    outline: Polygon  # the walls and their eaves, seen from above
    angle_deg: float  # the long walls' direction, anticlockwise from east, in [0, 180)
    clearances: Mapping[str, float]  # metres, as the evaluator measured them
    lowest_ground_m: float  # under the walls, as the floor-level check measures it
    highest_ground_m: float
    checks: tuple[Check, ...]  # the evaluator's siting verdicts on it

    def __post_init__(self) -> None:
        object.__setattr__(self, "clearances", MappingProxyType(dict(self.clearances)))

    @property
    def floor_range_m(self) -> tuple[float, float]:
        """The floor levels that pass: not below the highest ground (a cut is
        unknown), at most the rule's 1 m above the lowest."""
        return self.highest_ground_m, self.lowest_ground_m + MAX_FLOOR_ABOVE_GROUND_M

    @property
    def margin_m(self) -> float:
        """The least clearance to a line kept 2 m away."""
        return min(v for k, v in self.clearances.items() if k in _CLEARANCES.values())


@dataclass(frozen=True)
class Solution:
    placements: tuple[Placement, ...]  # best first
    # the least LiDAR range under the walls anywhere the outline fits the room
    # (a lower bound of the evaluator's); None if it fits nowhere
    least_ground_range_m: float | None


@dataclass(frozen=True)
class _Tried:
    walls: list[Polygon]
    outlines: list[Polygon]
    angles: list[float]


def solve(
    site: SiteContext,
    length_m: float,
    width_m: float,
    eaves_m: float = 0.0,
    count: int = 3,
    section_clear_m: float = MIN_SEPARATION_M,
    frontages: Sequence[Frontage] | None = None,
    angle_step_deg: float = ANGLE_STEP_DEG,
) -> Solution:
    """Up to ``count`` placements of the plan on ``site`` passing every siting
    check, best first. Below 2 m, ``section_clear_m`` lets a section line come
    back unknown (never crossed)."""
    title, lines = checks.title_and_internal_lines(site)
    room = _room(site, lines, section_clear_m)
    tried = _tried(room, site, length_m, width_m, eaves_m, angle_step_deg)
    if not tried.walls:
        return Solution((), None)
    spread = _cell_spread(tried.walls, site)
    chosen: list[Placement] = []
    asked = 0
    for i in _ranked(tried, spread, title, lines, site, _street(frontages)):
        walls, outline = tried.walls[i], tried.outlines[i]
        if any(walls.intersection(c.walls).area >= 0.5 * walls.area - _EPS for c in chosen):
            continue
        if asked == MAX_CONFIRMED:
            break
        asked += 1
        placement = confirmed_placement(site, title, lines, walls, outline, tried.angles[i])
        if placement is not None and _clear_enough(placement, section_clear_m):
            chosen.append(_with_street(placement, frontages))
            if len(chosen) == count:
                break
    return Solution(tuple(chosen), float(spread.min()))


def least_ground_range(
    site: SiteContext,
    length_m: float,
    width_m: float,
    eaves_m: float = 0.0,
    section_clear_m: float = MIN_SEPARATION_M,
    angle_step_deg: float = ANGLE_STEP_DEG,
) -> float | None:
    """``Solution.least_ground_range_m`` without asking the evaluator: the
    least LiDAR range under the walls at any pose tried where the outline
    fits the room; None if it fits at none."""
    _, lines = checks.title_and_internal_lines(site)
    room = _room(site, lines, section_clear_m)
    tried = _tried(room, site, length_m, width_m, eaves_m, angle_step_deg)
    return float(_cell_spread(tried.walls, site).min()) if tried.walls else None


def _room(site: SiteContext, lines: BaseGeometry, section_clear_m: float) -> BaseGeometry:
    room = room_of(site.parcels, site.confirmed_buildings, site.preservation_areas)
    if not lines.is_empty and section_clear_m > 0:
        room = room.difference(buffer_at_least(lines, section_clear_m))
    return room.buffer(-ROUNDING_M, join_style="mitre")


def _tried(
    room: BaseGeometry,
    site: SiteContext,
    length_m: float,
    width_m: float,
    eaves_m: float,
    angle_step_deg: float,
) -> _Tried:
    """The plan's walls and outline at every angle and grid point over
    ``room`` where the outline lies in it. The grid is ``GRID_M`` unless that
    would put more than about ``MAX_CANDIDATES`` in the room; then it is coarser."""
    tried = _Tried([], [], [])
    if room.is_empty:
        return tried
    steps = np.arange(0.0, 180.0, angle_step_deg)
    west, south, east, north = room.bounds
    grid = max(GRID_M, math.sqrt(room.area * len(steps) / MAX_CANDIDATES))
    xs, ys = np.meshgrid(np.arange(west, east, grid), np.arange(south, north, grid))
    shapely.prepare(room)
    inside_room = shapely.contains_xy(room, xs.ravel(), ys.ravel())  # an outline's centre is
    centres = np.column_stack([xs.ravel()[inside_room], ys.ravel()[inside_room]])
    first = longest_edge_angle(site.parcels) % 180.0
    for step in steps:
        angle = float((first + step) % 180.0)
        grown = (length_m + 2 * eaves_m, width_m + 2 * eaves_m)
        outlines = _rectangles(centres, *grown, angle)
        inside: NDArray[np.bool_] = shapely.covers(room, outlines)
        tried.outlines.extend(cast(list[Polygon], outlines[inside].tolist()))
        walls = _rectangles(centres[inside], length_m, width_m, angle)
        tried.walls.extend(cast(list[Polygon], walls.tolist()))
        tried.angles.extend([angle] * int(inside.sum()))
    return tried


def _rectangles(
    centres: NDArray[np.float64], length: float, width: float, angle_deg: float
) -> NDArray[np.object_]:
    """A ``length`` x ``width`` rectangle about each centre, its length at ``angle_deg``."""
    a = math.radians(angle_deg)
    along = np.array([math.cos(a), math.sin(a)]) * length / 2
    across = np.array([-math.sin(a), math.cos(a)]) * width / 2
    corners = np.array([along + across, -along + across, -along - across, along - across])
    rings = centres[:, None, :] + corners[None, :, :]
    closed = np.concatenate([rings, rings[:, :1]], axis=1)
    return cast(NDArray[np.object_], shapely.polygons(closed))


def _cell_spread(walls: list[Polygon], site: SiteContext) -> NDArray[np.float64]:
    """Highest less lowest LiDAR cell centre inside each of ``walls``: the
    floor-level check's samples less the outline's crossings."""
    grid = site.terrain
    rows, cols = grid.dem.shape
    xs = grid.bbox[0] + (np.arange(cols, dtype=np.float64) + 0.5) * grid.cell_m
    ys = grid.bbox[3] - (np.arange(rows, dtype=np.float64) + 0.5) * grid.cell_m
    x, y = np.meshgrid(xs, ys)
    tree = shapely.STRtree(cast(NDArray[np.object_], shapely.points(x.ravel(), y.ravel())))
    which, cell = cast(NDArray[np.intp], tree.query(walls, predicate="contains"))
    heights = grid.dem.ravel()[cell]
    low = np.full(len(walls), np.inf)
    high = np.full(len(walls), -np.inf)
    np.minimum.at(low, which, heights)
    np.maximum.at(high, which, heights)
    spread: NDArray[np.float64] = np.where(np.isfinite(low), high - low, 0.0)
    return spread


def _ranked(
    tried: _Tried,
    spread: NDArray[np.float64],
    title: BaseGeometry,
    lines: BaseGeometry,
    site: SiteContext,
    street: BaseGeometry,
) -> list[int]:
    """The candidates whose cells are flat enough, best first, by the stated
    preference."""
    flat = np.flatnonzero(spread <= MAX_FLOOR_ABOVE_GROUND_M + _EPS)
    outlines = np.array(tried.outlines, dtype=object)[flat]
    near = [title.boundary, lines, union_all([Polygon(r) for r in site.confirmed_buildings])]
    margin = np.full(len(flat), np.inf)
    for geometry in near:
        if not geometry.is_empty:
            margin = np.minimum(margin, _distances(outlines, geometry))
    walls = np.array(tried.walls, dtype=object)[flat]
    far = np.zeros(len(flat)) if street.is_empty else _distances(walls, street)
    ground = np.round(spread[flat] / GROUND_STEP_M)
    order = np.lexsort((-far, ground, -np.minimum(margin, TARGET_MARGIN_M)))
    return cast(list[int], flat[order].tolist())


def _distances(shapes: NDArray[np.object_], to: BaseGeometry) -> NDArray[np.float64]:
    found: NDArray[np.float64] = shapely.distance(shapes, to)  # pyright: ignore[reportUnknownMemberType]
    return found


def confirmed_placement(
    site: SiteContext,
    title: Polygon | MultiPolygon,
    lines: BaseGeometry,
    walls: Polygon,
    outline: Polygon,
    angle_deg: float,
) -> Placement | None:
    """The placement as the evaluator measures it; None if any siting check
    fails it. Unknowns that no placement can resolve are kept: separation
    from an unconfirmed list of buildings, a section line nearer than 2 m."""
    try:
        lowest, highest = checks.ground_range(walls, site.terrain)
    except InvalidProposal:  # off the measured terrain: never placed
        return None
    ring = tuple((float(x), float(y)) for x, y in walls.exterior.coords)
    proposal = Proposal(footprint=ring, floor_level_m=highest)
    verdicts = (
        checks.within_site(outline, title),
        checks.title_boundary_setback(outline, title),
        checks.section_boundary_setback(outline, lines),
        checks.building_separation(outline, site),
        checks.preservation_areas(outline, site),
        checks.floor_level(walls, proposal, site),
    )
    if any(v.status is Status.FAIL for v in verdicts) or verdicts[-1].status is not Status.PASS:
        return None
    clearances = {
        _CLEARANCES[v.name]: float(v.measured["distance_m"])
        for v in verdicts
        if v.name in _CLEARANCES and "distance_m" in v.measured
    }
    return Placement(walls, outline, angle_deg, clearances, lowest, highest, verdicts)


def _clear_enough(placement: Placement, section_clear_m: float) -> bool:
    """Whether its verdicts are as ``section_clear_m`` asks: kept 2 m clear, a
    section line passes; nothing else may be unknown but separation from a
    list of buildings the owner hasn't confirmed complete."""
    allowed = {"building_separation"}
    if section_clear_m < MIN_SEPARATION_M:
        allowed.add("section_boundary_setback")
    return all(c.status is Status.PASS or c.name in allowed for c in placement.checks)


def _street(frontages: Sequence[Frontage] | None) -> BaseGeometry:
    """The title's edges along the address's street (or nearest it)."""
    edges = [LineString(edge) for f in frontages or () if f.street for edge in f.edges]
    return union_all(edges) if edges else shapely.GeometryCollection()


def _with_street(placement: Placement, frontages: Sequence[Frontage] | None) -> Placement:
    street = _street(frontages)
    if street.is_empty:
        return placement
    clearances = {**placement.clearances, "street_edge_m": placement.walls.distance(street)}
    return Placement(
        placement.walls,
        placement.outline,
        placement.angle_deg,
        clearances,
        placement.lowest_ground_m,
        placement.highest_ground_m,
        placement.checks,
    )


def describe_placements(
    site: DesignSite, product: Footprint | None = None, eaves_m: float = PROMPT_EAVES_M
) -> str:
    """For the design agent, in its local coordinates and scene z: the best
    placements of a ``product``'s footprint, or for a bespoke design the best
    of each of ``PROMPT_PLANS``; or why a plan has none."""
    if product is None:
        plans, count = PROMPT_PLANS, 1
    else:
        plans, count = ((product.length_m, product.width_m),), 3
    datum = float(site.scene["frame"]["datum_m"])
    lines = [
        f"- placements found by search, best first, with {eaves_m:g} m eaves all round: "
        "each passes the evaluator's title setback (with the eaves), section line (kept "
        f"{MIN_SEPARATION_M:g} m clear), kept area and floor level checks and is "
        f"{MIN_SEPARATION_M:g} m from every listed building, aiming "
        f"for {TARGET_MARGIN_M:g} m clear of each {MIN_SEPARATION_M:g} m line. Walls' "
        "corners in local x, y:"
    ]
    number = 0
    for length, width in plans:
        plan = f"{length:g} × {width:g} m plan"
        solution = solve(site.context, length, width, eaves_m, count, frontages=site.frontages)
        for placement in solution.placements:
            number += 1
            text = _placement_text(placement, site.frame.to_local, datum)
            lines.append(f"  - {number}: a {plan}: {text}")
        if not solution.placements:
            lines.append(f"  - a {plan}: {_none_placed(solution)}")
    lines.append(
        "  Stand the Dwelling's walls on one of these, unless the brief is better served "
        "elsewhere, with its floor's underside within that placement's range."
    )
    return "\n".join(lines) + "\n"


def _none_placed(solution: Solution) -> str:
    least = solution.least_ground_range_m
    if least is None:
        return "no placement: with the section lines kept clear, it fits nowhere in the room."
    if least <= MAX_FLOOR_ABOVE_GROUND_M:
        return "the search found no placement that passes every siting check."
    return (
        "no placement passes floor level: wherever it fits, the ground under it varies "
        f"by at least {least:.2f} m, more than the "
        f"{MAX_FLOOR_ABOVE_GROUND_M:g} m allowed."
    )


def _placement_text(placement: Placement, local: Callable[[Point], Point], datum: float) -> str:
    centre = local((placement.walls.centroid.x, placement.walls.centroid.y))
    corners = [local((float(x), float(y))) for x, y in list(placement.walls.exterior.coords)[:-1]]
    names = {
        "title_boundary_m": "the title boundary",
        "section_line_m": "the section line",
        "building_m": "the nearest listed building",
        "street_edge_m": "the street edge",
    }
    clear = ", ".join(
        f"{placement.clearances[k]:.2f} m from {name}"
        for k, name in names.items()
        if k in placement.clearances
    )
    low = math.ceil((placement.floor_range_m[0] - datum) * 100 - _EPS) / 100
    high = math.floor((placement.floor_range_m[1] - datum) * 100 + _EPS) / 100
    return (
        f"centre ({centre[0]:.2f}, {centre[1]:.2f}), long walls at "
        f"{placement.angle_deg:.1f}° from the x axis: "
        + ", ".join(f"({x:.2f}, {y:.2f})" for x, y in corners)
        + f"; {clear}; floor underside at z {low:.2f} to {high:.2f}."
    )
