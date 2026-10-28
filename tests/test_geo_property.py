"""Tests for button_nz.geo.property, replaying recorded ArcGIS responses."""

from pathlib import Path

import httpx
import pytest

from button_nz.config import ServiceEndpoints
from button_nz.geo.property import (
    PropertyLayers,
    buildings_in,
    find_address,
    parcels_for_valuation,
)

FIXTURES = Path(__file__).parent / "fixtures" / "arcgis"
SITE = (1505926.13, 5336777.48, 1505969.74, 5336822.22)


def _layers(fixture: str) -> PropertyLayers:
    body = (FIXTURES / fixture).read_text(encoding="utf-8")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body)))
    return PropertyLayers.from_endpoints(ServiceEndpoints(), client)


def test_layers_point_at_the_right_feature_layers() -> None:
    layers = _layers("address_3213224.geojson")
    assert layers.addresses.url.endswith("LINZ_NZ_Addresses/FeatureServer/0")
    assert layers.parcels.url.endswith("BDC_Property_Master_Public_View/FeatureServer/1")
    assert layers.buildings.url.endswith("LINZ_NZ_Building_Outlines/FeatureServer/0")
    assert layers.parcels.attribution.startswith("Buller District Council")


def test_find_address() -> None:
    found = find_address(_layers("address_3213224.geojson").addresses, 3213224)
    assert found.value.address_id == 3213224
    assert found.value.full_address == "35 Victory Street, Reefton"
    assert found.value.point == pytest.approx((1505941.633, 5336793.693), abs=1e-3)
    assert found.provenance.query["where"] == "address_id=3213224"


def test_a_missing_address_raises() -> None:
    empty = '{"type": "FeatureCollection", "features": []}'
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=empty)))
    layers = PropertyLayers.from_endpoints(ServiceEndpoints(), client)
    with pytest.raises(LookupError, match="3213224"):
        find_address(layers.addresses, 3213224)


def test_parcels_for_valuation() -> None:
    found = parcels_for_valuation(_layers("parcels_1905027200.geojson").parcels, "1905027200")
    by_name = {p.appellation: p for p in found.value}
    assert set(by_name) == {
        "Section 700 TN OF Reefton",
        "Section 701 TN OF Reefton",
        "Section 702 TN OF Reefton",
        "Section 1336 TN OF Reefton",
    }
    assert by_name["Section 1336 TN OF Reefton"].parcel_id == 3625049
    assert by_name["Section 1336 TN OF Reefton"].survey_area_m2 == 30
    assert (
        by_name["Section 701 TN OF Reefton"].ring[0]
        == by_name["Section 701 TN OF Reefton"].ring[-1]
    )
    assert found.provenance.query["where"] == "ValNum='1905027200'"


def test_parcels_for_valuation_rejects_quotes() -> None:
    with pytest.raises(ValueError, match="valuation"):
        parcels_for_valuation(_layers("parcels_1905027200.geojson").parcels, "1' OR '1'='1")


def test_buildings_in() -> None:
    found = buildings_in(_layers("buildings_site.geojson").buildings, SITE)
    assert sorted(b.building_id for b in found.value) == [2517442, 2517444]
    assert {b.capture_source for b in found.value} == {
        "West Coast 0.3m Rural Aerial Photos (2015-2016)"
    }
    assert found.provenance.query["geometry"] == ",".join(str(v) for v in SITE)
