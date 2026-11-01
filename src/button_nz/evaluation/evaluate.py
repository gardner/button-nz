"""Evaluate a proposal: every check, every time, in a fixed order.

Where the building comes (site, setbacks, separation, preservation areas) is
measured from its outline, eaves included. Floor area and floor level are
measured from the outside of its external walls, as the exemption measures
them (MBIE guidance pp. 26 and 28). Floor area leaves out the open courtyards
those walls enclose; floor level keeps the ground under them (the stricter
reading). A placed product is checked first: its walls must be the product's
published footprint.
"""

from shapely import Polygon

from button_nz.evaluation import checks
from button_nz.evaluation.model import (
    Footprint,
    InvalidProposal,
    Proposal,
    Report,
    SiteContext,
    validate,
)
from button_nz.geo.geometry import Ring

_TOLERANCE_M = 1e-6


def evaluate(proposal: Proposal, site: SiteContext, product: Footprint | None = None) -> Report:
    """Raises InvalidProposal for a proposal that can't be evaluated. With
    ``product``, the walls are checked to be that product's footprint too."""
    validate(proposal)
    outer = _polygon(proposal.footprint, "footprint")
    walls = _with_courtyards(outer, proposal.courtyards)
    outline = outer if proposal.outline is None else _polygon(proposal.outline, "outline")
    if not outline.buffer(_TOLERANCE_M).contains(outer):
        raise InvalidProposal("the outline does not contain the wall footprint")
    title, internal_lines = checks.title_and_internal_lines(site)
    placed = () if product is None else (checks.product_footprint(walls, product),)
    return Report(
        (
            *placed,
            checks.within_site(outline, title),
            checks.title_boundary_setback(outline, title),
            checks.section_boundary_setback(outline, internal_lines),
            checks.building_separation(outline, site),
            checks.floor_area(walls, proposal),
            checks.single_storey(proposal),
            checks.height(proposal),
            checks.floor_level(outer, proposal, site),
            checks.preservation_areas(outline, site),
        )
    )


def _with_courtyards(outer: Polygon, courtyards: tuple[Ring, ...]) -> Polygon:
    """The walls' plan: ``outer`` with each open courtyard a hole in it."""
    if not courtyards:
        return outer
    walls = Polygon(outer.exterior, courtyards)
    if not walls.is_valid or any(Polygon(c).area <= 0 for c in courtyards):
        raise InvalidProposal("a courtyard is not a polygon inside the wall footprint")
    return walls


def _polygon(ring: Ring, name: str) -> Polygon:
    shape = Polygon(ring)
    if not shape.is_valid or shape.area <= 0:
        raise InvalidProposal(f"the {name} is not a valid polygon")
    return shape
