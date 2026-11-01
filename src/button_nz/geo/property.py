"""Typed property lookups: addresses (LINZ), parcels (Buller District Council)
and building outlines (LINZ), all in NZTM2000 with their provenance."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import httpx

from button_nz.config import ServiceEndpoints
from button_nz.geo.arcgis import Feature, FeatureLayer, Provenance
from button_nz.geo.geometry import BBox, Point, Ring

LINZ = "Toitū Te Whenua Land Information New Zealand"


@dataclass(frozen=True)
class Sourced[T]:
    """A value and where it came from."""

    value: T
    provenance: Provenance


@dataclass(frozen=True)
class Address:
    address_id: int
    full_address: str
    point: Point


@dataclass(frozen=True)
class Parcel:
    parcel_id: int
    appellation: str
    survey_area_m2: float | None
    titles: str | None
    ring: Ring


@dataclass(frozen=True)
class Building:
    building_id: int
    capture_source: str
    ring: Ring


# Buller District Council's ArcGIS items state no licence, so none is claimed:
# a use beyond reading them needs BDC's word, or the same data from a licensed
# source (the demo parcels match LINZ's CC BY 4.0 NZ Primary Parcels: data/README.md).
BDC_LICENCE = "not stated (the layer's ArcGIS item states none)"
BDC_ATTRIBUTION = "Buller District Council"


@dataclass(frozen=True)
class PropertyLayers:
    addresses: FeatureLayer
    parcels: FeatureLayer
    buildings: FeatureLayer

    @classmethod
    def from_endpoints(cls, endpoints: ServiceEndpoints, client: httpx.Client) -> PropertyLayers:
        return cls(
            addresses=FeatureLayer(f"{endpoints.linz_addresses_url}/0", "CC-BY-4.0", LINZ, client),
            parcels=FeatureLayer(
                f"{endpoints.buller_property_url}/1",
                BDC_LICENCE,
                BDC_ATTRIBUTION,
                client,
            ),
            buildings=FeatureLayer(f"{endpoints.linz_buildings_url}/0", "CC-BY-4.0", LINZ, client),
        )


def find_address(layer: FeatureLayer, address_id: int) -> Sourced[Address]:
    """The LINZ address with ``address_id``. Raises ``LookupError`` if absent."""
    found = layer.where(f"address_id={int(address_id)}")
    if len(found.features) != 1:
        raise LookupError(f"LINZ address {address_id}: {len(found.features)} matches")
    feature = found.features[0]
    props = _properties(feature)
    coordinates = cast("list[float]", _geometry(feature, "Point")["coordinates"])
    address = Address(
        address_id=int(props["address_id"]),
        full_address=str(props["full_address"]),
        point=(float(coordinates[0]), float(coordinates[1])),
    )
    return Sourced(address, found.provenance)


def parcels_for_valuation(
    layer: FeatureLayer, valuation_number: str
) -> Sourced[tuple[Parcel, ...]]:
    """Every Buller parcel on rating valuation ``valuation_number``."""
    if not re.fullmatch(r"[0-9A-Za-z/ ]+", valuation_number):
        raise ValueError(f"not a valuation number: {valuation_number!r}")
    found = layer.where(f"ValNum='{valuation_number}'")
    parcels = tuple(
        Parcel(
            parcel_id=int(props["ParcelID"]),
            appellation=str(props["Appellation"]),
            survey_area_m2=_optional_float(props.get("SurveyArea")),
            titles=_optional_str(props.get("Titles")),
            ring=_outer_ring(f),
        )
        for f in found.features
        for props in (_properties(f),)
    )
    return Sourced(parcels, found.provenance)


def buildings_in(layer: FeatureLayer, bbox: BBox) -> Sourced[tuple[Building, ...]]:
    """LINZ building outlines intersecting ``bbox`` (NZTM)."""
    found = layer.in_envelope(bbox)
    buildings = tuple(
        Building(
            building_id=int(props["building_id"]),
            capture_source=str(props["capture_source_name"]),
            ring=_outer_ring(f),
        )
        for f in found.features
        for props in (_properties(f),)
    )
    return Sourced(buildings, found.provenance)


def _properties(feature: Feature) -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", feature["properties"])


def _geometry(feature: Feature, kind: str) -> Mapping[str, Any]:
    geometry = cast("Mapping[str, Any] | None", feature.get("geometry"))
    if geometry is None or geometry.get("type") != kind:
        raise ValueError(f"expected {kind} geometry, got {geometry and geometry.get('type')}")
    return geometry


def _outer_ring(feature: Feature) -> Ring:
    rings = cast("list[list[list[float]]]", _geometry(feature, "Polygon")["coordinates"])
    if len(rings) != 1:
        raise ValueError(f"expected a polygon without holes, got {len(rings)} rings")
    return tuple((float(x), float(y)) for x, y, *_ in rings[0])


def _optional_float(value: object) -> float | None:
    return None if value is None else float(cast("float", value))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
