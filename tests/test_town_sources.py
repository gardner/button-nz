"""Tests for the town screen's sources: which parcels are residential
sections, and the building outlines around them."""

from typing import Any

import pytest
from shapely import box
from shapely.geometry import mapping

from button_nz.town.sources import outlines, residential_sections


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
    ]
    selection = residential_sections(parcels, ZONES)
    assert [s.parcel_id for s in selection.sections] == [1, 2]
    assert selection.sections[0].shape.equals(box(10, 10, 30, 40))
    assert selection.outside_zone == 2


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
