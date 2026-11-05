"""The instant massing (#188): where a home of a design's plan fits on its
site, known in well under a second as the design starts, long before Muse has
said anything. It is the placement solver's best (``agent.placement``), so
every siting check has passed it; the design is then free to stand elsewhere.

The plan is the prompt's: a placed product's footprint, or for a bespoke
design the first of ``PROMPT_PLANS`` that places, all with the prompt's eaves.
Its rings are in lon/lat for the web map, as the site's layers are.
"""

import time
from dataclasses import dataclass

from pydantic import BaseModel
from shapely import Polygon

from button_nz.agent.placement import PROMPT_EAVES_M, PROMPT_PLANS, Placement, solve
from button_nz.agent.site import DesignSite
from button_nz.evaluation import Footprint
from button_nz.geo.lonlat import TO_LONLAT

_DIGITS = 7  # about 1 cm, as the site's layers round them
_METRES = 3


@dataclass(frozen=True)
class Massing:
    length_m: float
    width_m: float
    eaves_m: float
    placement: Placement
    found_in_s: float  # after the job started


def massing_of(site: DesignSite, product: Footprint | None, started: float) -> Massing | None:
    """The best placement on ``site`` of the product's footprint, or of the
    first of the prompt's plans that places; None if none does. ``started``
    is the job's start, on ``time.monotonic``'s clock."""
    plans = PROMPT_PLANS if product is None else ((product.length_m, product.width_m),)
    for length, width in plans:
        found = solve(site.context, length, width, PROMPT_EAVES_M, 1, frontages=site.frontages)
        if found.placements:
            elapsed = time.monotonic() - started
            return Massing(length, width, PROMPT_EAVES_M, found.placements[0], elapsed)
    return None


class PlanView(BaseModel):
    length_m: float
    width_m: float
    eaves_m: float  # the outline is the walls grown by this all round


class PlacementView(BaseModel):
    """Where a home of ``plan`` fits, checked: provisional until Muse designs it."""

    plan: PlanView
    walls: list[list[float]]  # closed ring, [lon, lat]
    outline: list[list[float]]  # the walls and their eaves, seen from above
    # metres from the outline: title_boundary_m, section_line_m, building_m,
    # and from the walls street_edge_m, each where the site has one
    clearances: dict[str, float]
    floor_range_m: list[float]  # the floor underside's passing levels, LiDAR heights
    found_in_s: float  # how long after the job started it was known


def placement_view(massing: Massing) -> PlacementView:
    placement = massing.placement
    return PlacementView(
        plan=PlanView(length_m=massing.length_m, width_m=massing.width_m, eaves_m=massing.eaves_m),
        walls=lonlat_ring(placement.walls),
        outline=lonlat_ring(placement.outline),
        clearances={k: round(v, _METRES) for k, v in placement.clearances.items()},
        floor_range_m=[round(v, _METRES) for v in placement.floor_range_m],
        found_in_s=round(massing.found_in_s, _METRES),
    )


def lonlat_ring(polygon: Polygon) -> list[list[float]]:
    """``polygon``'s outside ring (NZTM), closed, as [lon, lat] pairs."""
    projected = (TO_LONLAT.transform(x, y) for x, y in polygon.exterior.coords)
    return [[round(lon, _DIGITS), round(lat, _DIGITS)] for lon, lat in projected]
