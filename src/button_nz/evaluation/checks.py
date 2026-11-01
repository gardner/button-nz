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

from button_nz.blender_worker.terrain_math import height_at, mesh_crossings
from button_nz.evaluation.model import (
    Check,
    Footprint,
    InvalidProposal,
    Proposal,
    SiteContext,
    Status,
)
from button_nz.geo.terrain import TerrainGrid

SCHEDULE_1A = (
    "Building Act 2004, Schedule 1A (granny flats exemption); "
    "MBIE Granny Flats Exemption Guidance, Dec 2025, p. 34"
)
NOT_OVER_ALLOTMENTS = (
    "Building Act 2004, s 42B: not built over a boundary between allotments, "
    "even on one record of title (MBIE guidance p. 53)"
)
MAX_FLOOR_AREA_M2 = 70.0
MAX_HEIGHT_ABOVE_FLOOR_M = 4.0
MAX_FLOOR_ABOVE_GROUND_M = 1.0
MIN_STOREY_M = 2.1  # the least headroom a storey can have (a doorway's height)
MIN_SEPARATION_M = 2.0  # from any legal boundary and any other residential building
TYPICAL_WALL_M = 0.3  # thickest common external wall (timber or steel frame, cladding)
MAX_WALL_M = 0.6  # thickest realistic external wall (straw bale, rammed earth, ICF)
EVIDENCE_HEIGHT_M = 2.0  # nDSM above this is reported as possible structure
PRODUCT_TOLERANCE_M = 0.10  # a placed product's walls may be this far off its footprint
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
    if footprint.buffer(-1e-6).intersects(internal_lines):  # through it, not just touching
        return Check(
            "section_boundary_setback",
            Status.FAIL,
            "The footprint is built over a line between two sections of the title.",
            {"distance_m": distance, "required_m": MIN_SEPARATION_M},
            NOT_OVER_ALLOTMENTS,
        )
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
    if not site.confirmed_buildings and site.buildings_confirmed:
        return Check(
            "building_separation",
            Status.PASS,
            "The owner confirms there are no other residential buildings on the title.",
            measured,
            SCHEDULE_1A,
        )
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
    detail = (
        f"{distance:.2f} m from the nearest listed building; "
        f"at least {MIN_SEPARATION_M:g} m required."
    )
    if distance < MIN_SEPARATION_M - _EPS:
        status = Status.FAIL  # too close to a listed building, complete list or not
    elif site.buildings_confirmed:
        status = Status.PASS
    else:  # an unlisted building could still be closer
        status = Status.UNKNOWN
        detail += (
            f" The owner hasn't confirmed the list is complete; LiDAR shows {evidence} cells "
            f"over {EVIDENCE_HEIGHT_M:g} m within {MIN_SEPARATION_M:g} m of the footprint."
        )
    return Check("building_separation", status, detail, measured, SCHEDULE_1A)


def product_footprint(walls: Polygon, product: Footprint) -> Check:
    """The walls are ``product``'s published outside footprint: a rectangle of
    its length and width, either way round, to within ``PRODUCT_TOLERANCE_M``.
    The walls lie inside their minimum rotated rectangle, so they are that
    rectangle when, grown by the tolerance, they cover all of it: an area test,
    not just their corners."""
    box = walls.minimum_rotated_rectangle
    corners = list(box.exterior.coords) if isinstance(box, Polygon) else []
    sides = sorted((_side(corners, 0), _side(corners, 1)), reverse=True)
    covered = walls.buffer(PRODUCT_TOLERANCE_M).contains(box)
    off = _farthest_from(walls, box)
    measured = {
        "length_m": sides[0],
        "width_m": sides[1],
        "off_rectangle_m": off,
        "product_length_m": product.length_m,
        "product_width_m": product.width_m,
        "tolerance_m": PRODUCT_TOLERANCE_M,
    }
    size = f"{product.length_m:g} × {product.width_m:g} m"
    rule = f"the {product.name}'s published outside footprint, {size}, to {PRODUCT_TOLERANCE_M:g} m"
    built = f"{sides[0]:.1f} × {sides[1]:.1f} m"
    want = sorted((product.length_m, product.width_m), reverse=True)
    if not covered:
        detail = (
            f"The walls are not a rectangle: up to {off:.2f} m off the {built} box around them."
        )
        return Check("product_footprint", Status.FAIL, detail, measured, rule)
    if any(abs(s - w) > PRODUCT_TOLERANCE_M for s, w in zip(sides, want, strict=True)):
        detail = f"The walls are {built}; the {product.name} is {size}."
        return Check("product_footprint", Status.FAIL, detail, measured, rule)
    detail = f"The walls are {built}, the {product.name}'s {size}."
    return Check("product_footprint", Status.PASS, detail, measured, rule)


def _farthest_from(walls: Polygon, box: BaseGeometry, step_m: float = 0.05) -> float:
    """How far the box's edge gets from the walls, sampled every ``step_m``."""
    if not isinstance(box, Polygon):
        return 0.0
    edge = box.exterior
    stops = np.arange(0.0, edge.length, step_m)
    return max(walls.distance(edge.interpolate(float(d))) for d in stops)


def _side(corners: list[tuple[float, ...]], k: int) -> float:
    (x0, y0, *_), (x1, y1, *_) = corners[k], corners[k + 1]
    return float(np.hypot(x1 - x0, y1 - y0))


def floor_area(footprint: Polygon, proposal: Proposal) -> Check:
    """Internal floor area <= 70 m², bounded by the measured footprint: the
    inside can't exceed the outside of the walls, and no realistic wall is more
    than ``MAX_WALL_M`` thick. Geometry decides where it can; a stated area that
    only unusually thick walls explain is unknown, not failed. An open courtyard
    is a hole in the footprint, not floor; the walls round it are not credited
    with any thickness (the stricter reading)."""
    outside, perimeter = footprint.area, footprint.exterior.length
    typical_inside = outside - perimeter * TYPICAL_WALL_M
    least_inside = outside - perimeter * MAX_WALL_M
    stated = proposal.floor_area_m2
    measured: dict[str, float] = {
        "footprint_area_m2": outside,
        "least_internal_area_m2": least_inside,
        "maximum": MAX_FLOOR_AREA_M2,
    } | _courtyard_area(footprint)
    if stated is not None:
        measured["value"] = stated
    rule = f"{SCHEDULE_1A}; walls at most {MAX_WALL_M:g} m thick"
    if stated is not None and stated > MAX_FLOOR_AREA_M2 + _EPS:  # stated over the limit
        detail = f"The stated internal area is {stated:g} m²; at most {MAX_FLOOR_AREA_M2:g}."
        return Check("floor_area", Status.FAIL, detail, measured, rule)
    if outside <= MAX_FLOOR_AREA_M2 + _EPS:  # geometry decides; a stated area can't fail it
        detail = f"The footprint is {outside:.1f} m², so the inside is under {MAX_FLOOR_AREA_M2:g}."
        if stated is not None and stated > outside + _EPS:
            detail += (
                f" The stated {stated:g} m² is more than the {outside:.1f} m² footprint"
                " (it may be the gross area). Check the stated value."
            )
        elif stated is not None and stated < typical_inside - _EPS:
            detail += f" {_thick_walls(stated, outside, typical_inside)} Check the stated value."
        return Check("floor_area", Status.PASS, detail, measured, rule)
    if stated is not None and stated > outside + _EPS:
        detail = f"The stated {stated:g} m² is more than the footprint's {outside:.1f} m²."
        return Check("floor_area", Status.FAIL, detail, measured, rule)
    if least_inside > MAX_FLOOR_AREA_M2 + _EPS:
        detail = (
            f"The footprint is {outside:.1f} m²: even with {MAX_WALL_M:g} m walls the inside "
            f"is at least {least_inside:.1f} m², over {MAX_FLOOR_AREA_M2:g}."
        )
        return Check("floor_area", Status.FAIL, detail, measured, rule)
    if stated is None:
        detail = (
            f"The footprint is {outside:.1f} m²; the internal area depends on the walls: state it."
        )
        return Check("floor_area", Status.UNKNOWN, detail, measured, rule)
    status, detail = _stated_area(stated, outside, typical_inside, least_inside)
    return Check("floor_area", status, detail, measured, rule)


def _courtyard_area(footprint: Polygon) -> dict[str, float]:
    """The open courtyards' area, to report beside the footprint's (if it has any)."""
    if not footprint.interiors:
        return {}
    return {"courtyard_area_m2": sum(Polygon(ring).area for ring in footprint.interiors)}


def _stated_area(
    stated: float, outside: float, typical_inside: float, least_inside: float
) -> tuple[Status, str]:
    """The verdict on a stated area, for a footprint that walls could bring under 70."""
    if stated < least_inside - _EPS:
        return Status.FAIL, (
            f"The stated {stated:g} m² is less than any wall up to {MAX_WALL_M:g} m thick "
            f"could leave inside this {outside:.1f} m² footprint ({least_inside:.1f} m²)."
        )
    if stated > MAX_FLOOR_AREA_M2 + _EPS:
        return Status.FAIL, (
            f"{stated:g} m² internal floor area; at most {MAX_FLOOR_AREA_M2:g} allowed."
        )
    if stated < typical_inside - _EPS:
        return Status.UNKNOWN, (
            f"{_thick_walls(stated, outside, typical_inside)} Confirm the wall thickness."
        )
    return Status.PASS, (
        f"{stated:g} m² internal floor area; at most {MAX_FLOOR_AREA_M2:g} allowed."
    )


def _thick_walls(stated: float, outside: float, typical_inside: float) -> str:
    return (
        f"The stated {stated:g} m² needs walls over {TYPICAL_WALL_M:g} m thick in this "
        f"{outside:.1f} m² footprint ({typical_inside:.1f} m² inside {TYPICAL_WALL_M:g} m walls)."
    )


def height(proposal: Proposal) -> Check:
    return _limit(
        "height", proposal.height_above_floor_m, MAX_HEIGHT_ABOVE_FLOOR_M, "m above the floor"
    )


def single_storey(proposal: Proposal) -> Check:
    """Single storey, from the measured height: a storey needs ``MIN_STOREY_M`` of
    headroom, so a building lower than two of them can't have two. A stated
    count over one fails; a stated one is only a claim, never a pass on its own."""
    rule = f"{SCHEDULE_1A}; a storey needs at least {MIN_STOREY_M:g} m of headroom"
    height, stated = proposal.height_above_floor_m, proposal.storeys
    measured: dict[str, float] = {} if height is None else {"height_above_floor_m": height}
    if stated is not None:
        measured["stated_storeys"] = stated
    if stated is not None and stated > 1:
        detail = f"The design has {stated} storeys; single storey required."
        return Check("single_storey", Status.FAIL, detail, measured, rule)
    if height is not None and height < 2 * MIN_STOREY_M:
        detail = f"{height:.2f} m above the floor leaves no room for a second storey."
        return Check("single_storey", Status.PASS, detail, measured, rule)
    detail = "The outside envelope can't show internal floors; the storeys are unmeasured."
    return Check("single_storey", Status.UNKNOWN, detail, measured, rule)


def floor_level(footprint: Polygon, proposal: Proposal, site: SiteContext) -> Check:
    lowest, highest = ground_range(footprint, site.terrain)
    measured = {"lowest_ground_m": lowest, "highest_ground_m": highest}
    if proposal.floor_level_m is None:
        return Check("floor_level", Status.UNKNOWN, "Floor level not given.", measured, SCHEDULE_1A)
    above = proposal.floor_level_m - lowest
    measured |= {"floor_level_m": proposal.floor_level_m, "height_above_lowest_m": above}
    if above > MAX_FLOOR_ABOVE_GROUND_M + _EPS:
        status, detail = Status.FAIL, f"The floor is {above:.2f} m above the lowest ground."
    elif proposal.floor_level_m < highest:  # a cut: allowed, but finished ground is unknown
        status, detail = (
            Status.UNKNOWN,
            f"The floor is below the existing ground ({highest:.2f} m) in places, so the site "
            "would be cut; the LiDAR shows only the ground before earthworks.",
        )
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
    areas = union_all([Polygon(a) for a in site.preservation_areas])
    overlap = footprint.intersection(areas).area
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


def _cell_centres(grid: TerrainGrid) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """NZTM x and y of every cell centre, shaped like the grid."""
    rows, cols = grid.dem.shape
    xs = grid.bbox[0] + (np.arange(cols, dtype=np.float64) + 0.5) * grid.cell_m
    ys = grid.bbox[3] - (np.arange(rows, dtype=np.float64) + 0.5) * grid.cell_m
    x, y = np.meshgrid(xs, ys)
    return x, y


def ground_range(footprint: Polygon, grid: TerrainGrid) -> tuple[float, float]:
    """Lowest and highest ground under the footprint: every cell centre inside it,
    plus every point where its outline crosses a terrain-mesh triangle edge,
    interpolated on the same triangles as the rendered terrain. The design
    model's elevation observations report the same range."""
    heights = _height_grid(grid)
    ring = [[float(x), float(y)] for x, y in footprint.exterior.coords]
    outline = mesh_crossings(ring, heights)
    if not all(_on_grid(grid, x, y) for x, y in outline):
        raise InvalidProposal("the terrain grid does not cover the whole footprint")
    samples = [height_at(heights, x, y) for x, y in outline]
    x, y = _cell_centres(grid)
    inside = shapely.contains_xy(footprint, x, y)
    samples += [float(h) for h in grid.dem[inside]]
    return min(samples), max(samples)


def _height_grid(grid: TerrainGrid) -> dict[str, object]:
    """The terrain in the scene's height-grid form (samples at cell centres)."""
    rows, cols = grid.dem.shape
    return {
        "rows": rows,
        "cols": cols,
        "cell_m": grid.cell_m,
        "x0": grid.bbox[0] + grid.cell_m / 2,
        "y0": grid.bbox[3] - grid.cell_m / 2,
        "heights": [float(h) for h in grid.dem.ravel()],
    }


def _on_grid(grid: TerrainGrid, x: float, y: float) -> bool:
    """Whether (x, y) lies within the cell centres, where heights are measured."""
    half = grid.cell_m / 2
    return (
        grid.bbox[0] + half - _EPS <= x <= grid.bbox[2] - half + _EPS
        and grid.bbox[1] + half - _EPS <= y <= grid.bbox[3] - half + _EPS
    )


def _lidar_cells_near(footprint: Polygon, site: SiteContext) -> int:
    x, y = _cell_centres(site.terrain)
    near = shapely.contains_xy(footprint.buffer(MIN_SEPARATION_M), x, y)
    return int((near & (site.terrain.ndsm > EVIDENCE_HEIGHT_M)).sum())
