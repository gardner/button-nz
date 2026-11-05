"""The placements a design is offered, numbered, in the model's local frame and
scene z: where its walls can stand (``placement.solve``) and the floor levels
that pass there. A design spec names one by number, and ``agent.build`` builds
on it, so the walls are always where the solver verified them.

A bespoke design is offered the best placement of each of ``PROMPT_PLANS``; a
placed product, its footprint's best three. Each plan is also offered its
placement nearest the street (where there is a street edge), for a design the
owner wants as near the street as the rules allow.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from button_nz.agent.placement import (
    PROMPT_EAVES_M,
    PROMPT_PLANS,
    TARGET_MARGIN_M,
    Placement,
    Solution,
    solve,
)
from button_nz.agent.site import DesignSite
from button_nz.agent.spec import Side
from button_nz.evaluation import Footprint
from button_nz.evaluation.checks import MAX_FLOOR_ABOVE_GROUND_M, MIN_SEPARATION_M
from button_nz.geo.geometry import Point

_EPS = 1e-9
COMPASS: tuple[Side, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_NAMES = {
    "title_boundary_m": "the title boundary",
    "section_line_m": "the section line",
    "building_m": "the nearest listed building",
    "street_edge_m": "the street edge",
}


@dataclass(frozen=True)
class Offer:
    """A placement offered to the design: a ``length_m`` x ``width_m`` plan of
    walls (outside) about ``centre`` (local), its long walls at ``angle_deg``
    anticlockwise from the x axis."""

    number: int
    centre: Point
    angle_deg: float
    length_m: float
    width_m: float
    floor_range: tuple[float, float]  # the floor underside's scene z that passes there
    summary: str  # where it is and how clear, as the prompt gives it

    def sides(self) -> dict[Side, tuple[float, float]]:
        """Each wall by the compass point it faces, with its outward direction
        in the plan's own frame (along the long walls, across them)."""
        across = math.radians(self.angle_deg + 90.0)  # the long walls' outward normal
        bearing = math.degrees(math.atan2(math.cos(across), math.sin(across)))
        k = math.floor(bearing / 45.0 + 0.5)  # nearest compass point; the rest are 90° on
        outward = ((0.0, 1.0), (1.0, 0.0), (0.0, -1.0), (-1.0, 0.0))  # +across, then clockwise
        return {COMPASS[(k + 2 * i) % 8]: d for i, d in enumerate(outward)}


@dataclass(frozen=True)
class Offers:
    offers: tuple[Offer, ...]
    missing: tuple[str, ...]  # for each plan with none, why
    eaves_m: float  # the outline the siting checks were passed with

    def get(self, number: int) -> Offer | None:
        return next((o for o in self.offers if o.number == number), None)


def offered(
    site: DesignSite, product: Footprint | None = None, eaves_m: float = PROMPT_EAVES_M
) -> Offers:
    """The placements a design on ``site`` (of a ``product``, or bespoke) is offered."""
    if product is None:
        plans, count = PROMPT_PLANS, 1
    else:
        plans, count = ((product.length_m, product.width_m),), 3
    datum = float(site.scene["frame"]["datum_m"])
    found: list[Offer] = []
    missing: list[str] = []
    for length, width in plans:
        solution = solve(site.context, length, width, eaves_m, count, frontages=site.frontages)
        placements = list(solution.placements)
        if placements and site.frontages:
            near = solve(
                site.context,
                length,
                width,
                eaves_m,
                1,
                frontages=site.frontages,
                nearest_street=True,
            )
            placements += [p for p in near.placements if not _overlaps(p, placements)]
        for placement in placements:
            found.append(_offer(len(found) + 1, length, width, placement, site, datum))
        if not placements:
            missing.append(f"a {length:g} × {width:g} m plan: {_none_placed(solution)}")
    return Offers(tuple(found), tuple(missing), eaves_m)


def _overlaps(placement: Placement, others: list[Placement]) -> bool:
    """Whether ``placement`` shares half its walls with one of ``others``: the same spot."""
    walls = placement.walls
    return any(walls.intersection(o.walls).area >= 0.5 * walls.area - _EPS for o in others)


def _offer(
    number: int, length: float, width: float, placement: Placement, site: DesignSite, datum: float
) -> Offer:
    local = site.frame.to_local
    centre = local((placement.walls.centroid.x, placement.walls.centroid.y))
    low, high = (level - datum for level in placement.floor_range_m)
    summary = _summary(placement, local, centre, (low, high))
    return Offer(number, centre, placement.angle_deg, length, width, (low, high), summary)


def _summary(
    placement: Placement,
    local: Callable[[Point], Point],
    centre: Point,
    floor: tuple[float, float],
) -> str:
    corners = [local((float(x), float(y))) for x, y in list(placement.walls.exterior.coords)[:-1]]
    clear = _clearances(placement.clearances)
    return (
        f"centre ({centre[0]:.2f}, {centre[1]:.2f}), long walls at "
        f"{placement.angle_deg:.1f}° from the x axis, corners "
        + ", ".join(f"({x:.2f}, {y:.2f})" for x, y in corners)
        + f"; {clear}; floor underside at z {floor_range_text(*floor)}"
    )


def _clearances(clearances: Mapping[str, float]) -> str:
    return ", ".join(
        f"{clearances[k]:.2f} m from {name}" for k, name in _NAMES.items() if k in clearances
    )


def heading(eaves_m: float) -> str:
    """What every offered placement has passed, for the prompt."""
    return (
        f"placements found by search, with {eaves_m:g} m eaves all round: each passes the "
        "evaluator's title setback (with the eaves), section line (kept "
        f"{MIN_SEPARATION_M:g} m clear), kept area and floor level checks and is "
        f"{MIN_SEPARATION_M:g} m from every listed building, aiming for "
        f"{TARGET_MARGIN_M:g} m clear of each {MIN_SEPARATION_M:g} m line"
    )


def _none_placed(solution: Solution) -> str:
    """Why the search found none: it samples poses, so one it didn't try may pass."""
    least = solution.least_ground_range_m
    if least is None:
        return (
            "no placement found: with the section lines kept clear, the search fitted it "
            "at none of the positions and angles it tried (others may fit)."
        )
    if least <= MAX_FLOOR_ABOVE_GROUND_M:
        return "no placement found: none the search tried passes every siting check."
    return (
        "no placement found that passes floor level: at every position the search tried, "
        f"the ground under it varies by at least {least:.2f} m, more than the "
        f"{MAX_FLOOR_ABOVE_GROUND_M:g} m allowed (a position it didn't try may pass)."
    )


def floor_range_text(low: float, high: float) -> str:
    """``low`` to ``high``, each drawn in to the centimetre so both printed
    levels pass, or as finely as it takes for the range to hold one."""
    for places in range(2, 7):
        scale = 10**places
        inner = math.ceil(low * scale - _EPS) / scale, math.floor(high * scale + _EPS) / scale
        if inner[0] <= inner[1]:
            return f"{inner[0]:.{places}f} to {inner[1]:.{places}f}"
    return f"{low:.6f} to {high:.6f}"
