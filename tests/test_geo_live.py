"""Live checks of the real LINZ and Buller services against the verified demo
site (data/demo-site). Excluded by default; run with `pytest -m live`."""

import httpx
import pytest

from button_nz.config import ServiceEndpoints
from button_nz.demo_site import load_demo_site
from button_nz.geo.geometry import contains
from button_nz.geo.property import (
    PropertyLayers,
    buildings_in,
    find_address,
    parcels_for_valuation,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def layers() -> PropertyLayers:
    return PropertyLayers.from_endpoints(ServiceEndpoints(), httpx.Client(timeout=30))


def test_the_address_matches_the_manifest(layers: PropertyLayers) -> None:
    site = load_demo_site()
    found = find_address(layers.addresses, 3213224)
    assert found.value.full_address == site.name
    assert found.value.point == pytest.approx(site.address_nztm, abs=0.1)


def test_the_parcels_match_the_manifest(layers: PropertyLayers) -> None:
    site = load_demo_site()
    assert site.valuation_number is not None  # Buller's rating data names it
    found = parcels_for_valuation(layers.parcels, site.valuation_number)
    assert sorted(p.parcel_id for p in found.value) == sorted(p.parcel_id for p in site.parcels)


def test_no_building_outline_is_on_the_site(layers: PropertyLayers) -> None:
    site = load_demo_site()
    found = buildings_in(layers.buildings, site.extent_nztm)
    on_site = [
        b.building_id
        for b in found.value
        for p in site.parcels
        if any(contains(p.ring, corner) for corner in b.ring)
    ]
    assert on_site == []
