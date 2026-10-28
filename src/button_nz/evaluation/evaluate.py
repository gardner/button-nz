"""Evaluate a proposal: every check, every time, in a fixed order."""

from shapely import Polygon

from button_nz.evaluation import checks
from button_nz.evaluation.model import InvalidProposal, Proposal, Report, SiteContext, validate


def evaluate(proposal: Proposal, site: SiteContext) -> Report:
    """Raises InvalidProposal for a proposal that can't be evaluated."""
    validate(proposal)
    footprint = Polygon(proposal.footprint)
    if not footprint.is_valid or footprint.area <= 0:
        raise InvalidProposal("the footprint is not a valid polygon")
    title, internal_lines = checks.title_and_internal_lines(site)
    return Report(
        (
            checks.within_site(footprint, title),
            checks.title_boundary_setback(footprint, title),
            checks.section_boundary_setback(footprint, internal_lines),
            checks.building_separation(footprint, site),
            checks.floor_area(footprint, proposal),
            checks.single_storey(proposal),
            checks.height(proposal),
            checks.floor_level(footprint, proposal, site),
            checks.preservation_areas(footprint, site),
        )
    )
