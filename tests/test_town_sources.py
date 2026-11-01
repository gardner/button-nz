"""Tests for the town screen's sources: which parcels are residential
sections, and the building outlines around them."""

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from shapely import box
from shapely.geometry import mapping, shape

from button_nz.config import ServiceEndpoints
from button_nz.town.sources import (
    Section,
    buildings_on,
    fetch,
    outlines,
    residential_sections,
)


def feature(geometry: Any, **properties: Any) -> dict[str, Any]:
    return {"type": "Feature", "properties": properties, "geometry": mapping(geometry)}


ZONES = [
    feature(box(0, 0, 100, 100), ZONING="re", FULL_ZONE="RESIDENTIAL ZONE"),
    feature(box(200, 0, 300, 100), ZONING="re", FULL_ZONE="RESIDENTIAL ZONE"),
]


def test_a_parcel_is_a_section_when_its_point_lies_in_a_residential_zone() -> None:
    parcels = [
        feature(box(10, 10, 30, 40), ParcelID=1, ParcelIntent="DCDB"),
        feature(box(210, 10, 230, 40), ParcelID=2, ParcelIntent="Fee Simple Title"),
        feature(box(110, 10, 130, 40), ParcelID=3, ParcelIntent="DCDB"),  # between the zones
        feature(box(90, 10, 160, 40), ParcelID=4, ParcelIntent="DCDB"),  # mostly outside
        feature(box(110, 50, 190, 60), ParcelID=5, ParcelIntent="Road"),  # not a title
    ]
    selection = residential_sections(parcels, ZONES)
    assert [s.parcel_id for s in selection.sections] == [1, 2]
    assert selection.sections[0].shape.equals(box(10, 10, 30, 40))
    assert selection.outside_zone == 2  # titles only: the road outside isn't counted
    assert selection.other_intent == {}


def test_roads_and_reserves_are_not_sections() -> None:
    parcels = [
        feature(box(10, 10, 30, 40), ParcelID=1, ParcelIntent="Road"),
        feature(box(40, 10, 60, 40), ParcelID=2, ParcelIntent="Hydro"),
        feature(box(70, 10, 90, 40), ParcelID=3, ParcelIntent="DCDB"),
    ]
    selection = residential_sections(parcels, ZONES)
    assert [s.parcel_id for s in selection.sections] == [3]
    assert selection.other_intent == {"Road": 1, "Hydro": 1}


def test_a_parcel_in_parts_is_one_section() -> None:
    parts = box(10, 10, 20, 20).union(box(40, 40, 50, 50))
    selection = residential_sections([feature(parts, ParcelID=9, ParcelIntent="DCDB")], ZONES)
    assert selection.sections[0].shape.area == pytest.approx(200)


def test_a_repeated_parcel_id_is_refused() -> None:
    twice = [feature(box(10, 10, 20, 20), ParcelID=5, ParcelIntent="DCDB")] * 2
    with pytest.raises(ValueError, match="5"):
        residential_sections(twice, ZONES)


def test_outlines_are_polygons_and_parts_of_multipolygons() -> None:
    found = outlines(
        [
            feature(box(0, 0, 5, 5), building_id=1),
            feature(box(10, 0, 15, 5).union(box(20, 0, 25, 5)), building_id=2),
        ]
    )
    assert sorted(o.bounds[0] for o in found) == [0, 10, 20]


def test_a_feature_without_polygon_geometry_is_refused() -> None:
    point = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Point", "coordinates": [0, 0]},
    }
    with pytest.raises(ValueError, match="Point"):
        outlines([point])


def test_the_buildings_on_sections_are_those_touching_one() -> None:
    sections = [Section(1, box(0, 0, 10, 10)), Section(2, box(20, 0, 30, 10))]
    on, off = box(2, 2, 4, 4), box(50, 50, 52, 52)
    straddling = box(9, 2, 21, 4)
    assert buildings_on(sections, [on, off, straddling]) == (on, straddling)


def test_zones_and_outlines_are_fetched_for_everywhere_a_section_reaches() -> None:
    # A big parcel touches the envelope, but its point (225, 70) lies in a zone
    # that doesn't reach back into the envelope at all.
    big = feature(box(50, 50, 400, 90), ParcelID=1, ParcelIntent="DCDB")
    zone = feature(box(150, 0, 300, 100), ZONING="re")
    asked: dict[str, tuple[float, float, float, float]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        x0, y0, x1, y1 = (float(v) for v in params["geometry"].split(","))
        layer = "outlines" if "Building_Outlines" in url.path else "zones"
        layer = layer if "Property" not in url.path else "parcels"
        asked[layer] = (x0, y0, x1, y1)
        candidates = {"zones": [zone], "parcels": [big], "outlines": []}[layer]
        found = [f for f in candidates if shape(f["geometry"]).intersects(box(x0, y0, x1, y1))]
        return httpx.Response(
            200, text=json.dumps({"type": "FeatureCollection", "features": found})
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    data = fetch(ServiceEndpoints.from_env({}), client, (0.0, 0.0, 100.0, 100.0))
    assert [s.parcel_id for s in data.selection.sections] == [1]
    for layer in ("zones", "outlines"):
        west, south, east, north = asked[layer]
        assert west <= 50 and south <= 50 and east >= 400 and north >= 90, layer
    west, south, east, north = asked["outlines"]
    assert west <= 48 and south <= 48 and east >= 402 and north >= 92
