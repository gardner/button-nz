"""A small typed client for ArcGIS REST feature layers.

Every query asks for GeoJSON in NZTM2000 (``outSR=2193``), pages through the
server's transfer limit, and returns the features with their provenance.
ArcGIS reports failures as HTTP 200 with an ``error`` body, so those raise
``ArcGISError`` like HTTP failures do; an error is never read as "no features".
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from button_nz.geo.geometry import BBox, Point

type Feature = Mapping[str, Any]

NZTM = "2193"


class ArcGISError(RuntimeError):
    """An ArcGIS query failed."""


@dataclass(frozen=True)
class Provenance:
    """Where a result came from: enough to cite it and to repeat the query."""

    service: str
    query: Mapping[str, str]
    retrieved_at: datetime
    licence: str
    attribution: str


@dataclass(frozen=True)
class FeatureSet:
    features: tuple[Feature, ...]
    provenance: Provenance


@dataclass(frozen=True)
class FeatureLayer:
    """One feature layer, e.g. ``.../FeatureServer/0``."""

    url: str
    licence: str
    attribution: str
    client: httpx.Client
    order_by: str = "OBJECTID"

    def where(self, clause: str) -> FeatureSet:
        return self._query({"where": clause})

    def in_envelope(self, bbox: BBox) -> FeatureSet:
        return self._query(
            {
                "geometry": ",".join(str(v) for v in bbox),
                "geometryType": "esriGeometryEnvelope",
                "inSR": NZTM,
                "spatialRel": "esriSpatialRelIntersects",
            }
        )

    def near(self, point: Point, distance_m: float) -> FeatureSet:
        return self._query(
            {
                "geometry": f"{point[0]},{point[1]}",
                "geometryType": "esriGeometryPoint",
                "inSR": NZTM,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": str(distance_m),
                "units": "esriSRUnit_Meter",
            }
        )

    def _query(self, criteria: Mapping[str, str]) -> FeatureSet:
        query = {
            "where": "1=1",
            **criteria,
            "outFields": "*",
            "outSR": NZTM,
            "orderByFields": self.order_by,
            "f": "geojson",
        }
        retrieved_at = datetime.now(UTC)
        features: list[Feature] = []
        while True:
            page = self._get({**query, "resultOffset": str(len(features))})
            batch = cast("list[Feature]", page.get("features", []))
            features.extend(batch)
            if not _exceeded_transfer_limit(page) or not batch:
                break
        provenance = Provenance(self.url, query, retrieved_at, self.licence, self.attribution)
        return FeatureSet(tuple(features), provenance)

    def _get(self, params: Mapping[str, str]) -> Mapping[str, Any]:
        try:
            response = self.client.get(f"{self.url}/query", params=params)
            response.raise_for_status()
            body = cast("Mapping[str, Any]", json.loads(response.text))
        except (httpx.HTTPError, ValueError) as error:
            raise ArcGISError(f"{self.url}: {error}") from error
        if "error" in body:
            error = cast("Mapping[str, Any]", body["error"])
            details = "; ".join(str(d) for d in error.get("details") or [error.get("message")])
            raise ArcGISError(f"{self.url}: {error.get('code')} {details}")
        return body


def _exceeded_transfer_limit(page: Mapping[str, Any]) -> bool:
    properties = cast("Mapping[str, Any]", page.get("properties") or {})
    return bool(properties.get("exceededTransferLimit") or page.get("exceededTransferLimit"))
