"""A site as the API serves it (``GET /site``, and ``GET /sites/{id}`` once ready).

Each source is listed with what a person needs to cite and date it: its
title, collection or service, licence, attribution, capture dates and, for a
raster joined from tiles, the tiles. Never where the server keeps its own
copy.
"""

from datetime import datetime
from typing import Any

from button_nz.demo_site import DemoSite, RasterSource, VectorSource


def site_view(site: DemoSite) -> dict[str, Any]:
    features = [
        {
            "type": "Feature",
            "id": parcel.parcel_id,
            "properties": {"appellation": parcel.appellation},
            "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in parcel.ring]]},
        }
        for parcel in site.parcels
    ]
    sources = {name: _raster(r) for name, r in site.rasters.items()}
    sources |= {name: _vector(v) for name, v in site.vectors.items()}
    return {
        "name": site.name,
        "title": site.title,
        "valuation_number": site.valuation_number,
        "crs": "EPSG:2193",
        "address": list(site.address_nztm),
        "extent": list(site.extent_nztm),
        "parcels": {"type": "FeatureCollection", "features": features},
        "sources": sources,
        "open_items": list(site.open_items),
    }


def _raster(source: RasterSource) -> dict[str, Any]:
    tiles = list(source.tiles) if source.tile is None else [source.asset]
    return {
        "title": source.title,
        "collection": source.collection,
        "tiles": tiles,
        "resolution_m": source.resolution_m,
        "capture": _dates(source.capture.start, source.capture.end),
        "licence": source.licence,
        "attribution": source.attribution,
    }


def _vector(source: VectorSource) -> dict[str, Any]:
    capture = source.capture
    return {
        "title": source.title,
        "service": source.service,
        "licence": source.licence,
        "attribution": source.attribution,
        "capture": None if capture is None else _dates(capture.start, capture.end),
    }


def _dates(start: datetime, end: datetime) -> dict[str, str]:
    return {"start": start.isoformat(), "end": end.isoformat()}
