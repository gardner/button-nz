"""A town's residential sections and the building outlines on them, from
Buller District Council's parcels and zones and LINZ's building outlines.

A section is a BDC parcel whose representative point lies in a Residential
zone of BDC's published zones layer, and whose intent is a title
(``SECTION_INTENTS``): roads, rivers and reserves are not sections.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

import httpx
from shapely import MultiPolygon, Polygon, STRtree
from shapely.geometry import shape

from button_nz.config import ServiceEndpoints
from button_nz.geo.arcgis import Feature, FeatureLayer, FeatureSet
from button_nz.geo.geometry import BBox
from button_nz.geo.property import PropertyLayers

BDC_PLANNING_ZONES = (
    "https://services6.arcgis.com/Whb8vGWSmNkavSpL/arcgis/rest/services/"
    "BDC_Planning_Data_Public_View/FeatureServer/29"
)
BDC_ATTRIBUTION = "Buller District Council; LINZ, Crown copyright reserved"
RESIDENTIAL = "ZONING='re'"  # "RESIDENTIAL ZONE" in BDC's zones layer
SECTION_INTENTS = frozenset({"DCDB", "Fee Simple Title"})
# Reefton's Residential zones, to the next 100 m. Blacks Point's, 850 m to the
# south-east, are left out: (1507400, 5334600, 1507800, 5335400) covers them.
REEFTON: BBox = (1505100.0, 5336200.0, 1506700.0, 5337700.0)

type Area = Polygon | MultiPolygon


@dataclass(frozen=True)
class Section:
    parcel_id: int  # BDC's ParcelID
    shape: Area


@dataclass(frozen=True)
class Selection:
    sections: tuple[Section, ...]  # in ParcelID order
    outside_zone: int  # titles whose point is in no Residential zone
    other_intent: Mapping[str, int]  # in a Residential zone, but not a title


@dataclass(frozen=True)
class TownData:
    selection: Selection
    buildings: tuple[Polygon, ...]
    zones: FeatureSet
    parcels: FeatureSet
    outlines: FeatureSet


def fetch(endpoints: ServiceEndpoints, client: httpx.Client, bbox: BBox) -> TownData:
    """The sections in ``bbox`` and the building outlines around them."""
    layers = PropertyLayers.from_endpoints(endpoints, client)
    zone_layer = FeatureLayer(BDC_PLANNING_ZONES, "CC-BY-4.0", BDC_ATTRIBUTION, client)
    zones = zone_layer.in_envelope(bbox, where=RESIDENTIAL)
    parcels = layers.parcels.in_envelope(bbox)
    # Wide enough for a building just outside the envelope that is within
    # the separation distance of a section inside it.
    wider = (bbox[0] - 50, bbox[1] - 50, bbox[2] + 50, bbox[3] + 50)
    building_outlines = layers.buildings.in_envelope(wider)
    selection = residential_sections(parcels.features, zones.features)
    return TownData(
        selection, outlines(building_outlines.features), zones, parcels, building_outlines
    )


def residential_sections(parcels: Iterable[Feature], zones: Iterable[Feature]) -> Selection:
    """The ``parcels`` that are titles with their point in one of ``zones``."""
    zoned = STRtree([_area(z) for z in zones])
    sections: dict[int, Section] = {}
    outside, other = 0, Counter[str]()
    for feature in parcels:
        props = cast("Mapping[str, Any]", feature["properties"])
        area = _area(feature)
        point = area.representative_point()
        if not len(zoned.query(point, predicate="within")):
            outside += 1
            continue
        intent = str(props.get("ParcelIntent"))
        if intent not in SECTION_INTENTS:
            other[intent] += 1
            continue
        parcel_id = int(props["ParcelID"])
        if parcel_id in sections:
            raise ValueError(f"parcel {parcel_id} appears twice")
        sections[parcel_id] = Section(parcel_id, area)
    ordered = tuple(sections[k] for k in sorted(sections))
    return Selection(ordered, outside, dict(other))


def buildings_on(sections: Sequence[Section], buildings: Sequence[Polygon]) -> tuple[Polygon, ...]:
    """The ``buildings`` touching at least one of ``sections``, in order."""
    tree = STRtree([s.shape for s in sections])
    return tuple(b for b in buildings if len(tree.query(b, predicate="intersects")))


def outlines(features: Iterable[Feature]) -> tuple[Polygon, ...]:
    """Building outlines as polygons; a multipolygon gives each of its parts."""
    found: list[Polygon] = []
    for feature in features:
        area = _area(feature)
        found.extend(area.geoms if isinstance(area, MultiPolygon) else [area])
    return tuple(found)


def _area(feature: Feature) -> Area:
    geometry = cast("Mapping[str, Any] | None", feature.get("geometry"))
    kind = geometry.get("type") if geometry else None
    if geometry is None or kind not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"expected polygon geometry, got {kind}")
    return cast("Area", shape(dict(geometry)))
