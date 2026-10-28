"""The evaluator on the real demo site, with terrain from LINZ's public S3.
Excluded by default; run with `pytest -m live`."""

import pytest
from shapely import Polygon

from button_nz.demo_site import load_demo_site
from button_nz.evaluation import Proposal, SiteContext, Status, evaluate
from button_nz.geo.terrain import read_terrain

pytestmark = pytest.mark.live


def test_a_small_dwelling_at_the_site_centre() -> None:
    site = load_demo_site()
    terrain = read_terrain(
        site.rasters["dem"].asset, site.rasters["dsm"].asset, site.extent_nztm, margin_m=5.0
    )
    title = Polygon(site.parcels[0].ring).union(Polygon(site.parcels[1].ring))
    centre = title.centroid
    half_w, half_d = 3.0, 2.5  # a 6 m x 5 m footprint
    footprint = (
        (centre.x - half_w, centre.y - half_d),
        (centre.x + half_w, centre.y - half_d),
        (centre.x + half_w, centre.y + half_d),
        (centre.x - half_w, centre.y + half_d),
        (centre.x - half_w, centre.y - half_d),
    )
    context = SiteContext(parcels=tuple(p.ring for p in site.parcels), terrain=terrain)
    report = evaluate(Proposal(footprint=footprint, floor_area_m2=26.0, storeys=1), context)
    by_name = {c.name: c for c in report.checks}

    assert by_name["within_site"].status is Status.PASS
    # The sections are ~10 m wide strips: any placement is near an internal line.
    assert by_name["section_boundary_setback"].status is Status.UNKNOWN
    # The ground under the footprint is the measured Reefton ground (NZVD2016).
    lowest = by_name["floor_level"].measured["lowest_ground_m"]
    assert 189.0 < lowest < 191.5
    assert report.status is not Status.PASS
