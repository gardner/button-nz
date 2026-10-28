"""Deterministic checks of a proposal against a site.

Numbers come from Schedule 1A of the Building Act 2004 (the granny flats
building consent exemption, in force from 15 January 2026) as quoted in MBIE's
Granny Flats Exemption Guidance (December 2025), "What the law says", p. 34.
These checks are decision support, not a compliance or consent determination.
"""

import numpy as np
import shapely
from numpy.typing import NDArray
from shapely import MultiPolygon, Polygon, union_all
from shapely.geometry.base import BaseGeometry

from button_nz.evaluation.model import Check, Proposal, SiteContext, Status

SCHEDULE_1A = (
    "Building Act 2004, Schedule 1A (granny flats exemption); "
    "MBIE Granny Flats Exemption Guidance, Dec 2025, p. 34"
)
MAX_FLOOR_AREA_M2 = 70.0
MAX_HEIGHT_ABOVE_FLOOR_M = 4.0
MAX_FLOOR_ABOVE_GROUND_M = 1.0
MIN_SEPARATION_M = 2.0  # from any legal boundary and any other residential building
EVIDENCE_HEIGHT_M = 2.0  # nDSM above this is reported as possible structure
_EPS = 1e-9


def within_site(footprint: Polygon, title: Polygon | MultiPolygon) -> Check:
    outside = footprint.difference(title).area
    status = Status.PASS if outside <= 1e-6 else Status.FAIL
    return Check(
        "within_site",
        status,
        "The footprint lies on the title."
        if status is Status.PASS
        else f"{outside:.2f} m² of the footprint is outside the title.",
        {"area_outside_m2": outside},
        "Design brief: the dwelling must be on the owner's title",
    )


def title_boundary_setback(footprint: Polygon, title: Polygon | MultiPolygon) -> Check:
    distance = footprint.distance(title.boundary)
    status = Status.PASS if distance >= MIN_SEPARATION_M - _EPS else Status.FAIL
    return Check(
        "title_boundary_setback",
        status,
        f"{distance:.2f} m from the title boundary; at least {MIN_SEPARATION_M:g} m required.",
        {"distance_m": distance, "required_m": MIN_SEPARATION_M},
        SCHEDULE_1A,
    )


def section_boundary_setback(footprint: Polygon, internal_lines: BaseGeometry) -> Check:
    rule = (
        f"{SCHEDULE_1A}; whether lines between sections on one title "
        "are legal boundaries is unconfirmed"
    )
    if internal_lines.is_empty:
        return Check("section_boundary_setback", Status.PASS, "The title is one parcel.", {}, rule)
    distance = footprint.distance(internal_lines)
    if distance >= MIN_SEPARATION_M - _EPS:
        return Check(
            "section_boundary_setback",
            Status.PASS,
            f"{distance:.2f} m from the nearest internal section line.",
            {"distance_m": distance, "required_m": MIN_SEPARATION_M},
            rule,
        )
    return Check(
        "section_boundary_setback",
        Status.UNKNOWN,
        f"{distance:.2f} m from an internal section line. Within {MIN_SEPARATION_M:g} m, "
        "this fails only if that line counts as a legal boundary: confirm with a surveyor.",
        {"distance_m": distance, "required_m": MIN_SEPARATION_M},
        rule,
    )


def building_separation(footprint: Polygon, site: SiteContext) -> Check:
    evidence = _lidar_cells_near(footprint, site)
    measured: dict[str, float] = {
        "lidar_cells_over_2m_within_2m": float(evidence),
        "required_m": MIN_SEPARATION_M,
    }
    if not site.confirmed_buildings:
        return Check(
            "building_separation",
            Status.UNKNOWN,
            "No existing buildings are confirmed by the owner; "
            f"LiDAR shows {evidence} cells over {EVIDENCE_HEIGHT_M:g} m within "
            f"{MIN_SEPARATION_M:g} m of the footprint.",
            measured,
            SCHEDULE_1A,
        )
    distance = min(footprint.distance(Polygon(b)) for b in site.confirmed_buildings)
    measured["distance_m"] = distance
    status = Status.PASS if distance >= MIN_SEPARATION_M - _EPS else Status.FAIL
    return Check(
        "building_separation",
        status,
        f"{distance:.2f} m from the nearest confirmed building; "
        f"at least {MIN_SEPARATION_M:g} m required.",
        measured,
        SCHEDULE_1A,
    )


def floor_area(proposal: Proposal) -> Check:
    return _limit("floor_area", proposal.floor_area_m2, MAX_FLOOR_AREA_M2, "m² internal floor area")


def height(proposal: Proposal) -> Check:
    return _limit(
        "height", proposal.height_above_floor_m, MAX_HEIGHT_ABOVE_FLOOR_M, "m above the floor"
    )


def single_storey(proposal: Proposal) -> Check:
    if proposal.storeys is None:
        return Check("single_storey", Status.UNKNOWN, "Storeys not given.", {}, SCHEDULE_1A)
    status = Status.PASS if proposal.storeys == 1 else Status.FAIL
    detail = f"{proposal.storeys} storey(s); single storey required."
    return Check("single_storey", status, detail, {"storeys": proposal.storeys}, SCHEDULE_1A)


def floor_level(footprint: Polygon, proposal: Proposal, site: SiteContext) -> Check:
    lowest, highest = _ground_range(footprint, site)
    measured = {"lowest_ground_m": lowest, "highest_ground_m": highest}
    if proposal.floor_level_m is None:
        return Check("floor_level", Status.UNKNOWN, "Floor level not given.", measured, SCHEDULE_1A)
    above = proposal.floor_level_m - lowest
    measured |= {"floor_level_m": proposal.floor_level_m, "height_above_lowest_m": above}
    if proposal.floor_level_m < highest:
        status, detail = Status.FAIL, f"The floor is below the ground ({highest:.2f} m) in places."
    elif above > MAX_FLOOR_ABOVE_GROUND_M + _EPS:
        status, detail = Status.FAIL, f"The floor is {above:.2f} m above the lowest ground."
    else:
        status, detail = Status.PASS, f"The floor is {above:.2f} m above the lowest ground."
    return Check(
        "floor_level",
        status,
        f"{detail} At most {MAX_FLOOR_ABOVE_GROUND_M:g} m allowed.",
        measured,
        SCHEDULE_1A,
    )


def preservation_areas(footprint: Polygon, site: SiteContext) -> Check:
    rule = "The owner's preservation areas"
    if not site.preservation_areas:
        return Check("preservation_areas", Status.PASS, "No preservation areas given.", {}, rule)
    overlap = sum(footprint.intersection(Polygon(a)).area for a in site.preservation_areas)
    status = Status.PASS if overlap <= 1e-6 else Status.FAIL
    detail = f"{overlap:.2f} m² of the footprint is in a preservation area."
    return Check("preservation_areas", status, detail, {"overlap_m2": overlap}, rule)


def title_and_internal_lines(site: SiteContext) -> tuple[Polygon | MultiPolygon, BaseGeometry]:
    parcels = [Polygon(r) for r in site.parcels]
    title = union_all(parcels)
    if not isinstance(title, Polygon | MultiPolygon):
        raise ValueError("the parcels do not form an area")
    edges = union_all([p.boundary for p in parcels])
    return title, edges.difference(title.boundary.buffer(1e-6))


def _limit(name: str, value: float | None, maximum: float, unit: str) -> Check:
    if value is None:
        return Check(name, Status.UNKNOWN, "Not given.", {}, SCHEDULE_1A)
    status = Status.PASS if value <= maximum + _EPS else Status.FAIL
    detail = f"{value:g} {unit}; at most {maximum:g} allowed."
    return Check(name, status, detail, {"value": value, "maximum": maximum}, SCHEDULE_1A)


def _cell_centres(site: SiteContext) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """NZTM x and y of every cell centre, shaped like the grid."""
    grid = site.terrain
    rows, cols = grid.dem.shape
    xs = grid.bbox[0] + (np.arange(cols, dtype=np.float64) + 0.5) * grid.cell_m
    ys = grid.bbox[3] - (np.arange(rows, dtype=np.float64) + 0.5) * grid.cell_m
    x, y = np.meshgrid(xs, ys)
    return x, y


def _ground_range(footprint: Polygon, site: SiteContext) -> tuple[float, float]:
    x, y = _cell_centres(site)
    inside = shapely.contains_xy(footprint, x, y)
    if not inside.any():
        raise ValueError("the terrain grid has no cell centre inside the footprint")
    ground = site.terrain.dem[inside]
    return float(ground.min()), float(ground.max())


def _lidar_cells_near(footprint: Polygon, site: SiteContext) -> int:
    x, y = _cell_centres(site)
    near = shapely.contains_xy(footprint.buffer(MIN_SEPARATION_M), x, y)
    return int((near & (site.terrain.ndsm > EVIDENCE_HEIGHT_M)).sum())
