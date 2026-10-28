"""The verified demo site: 35 Victory Street, Reefton.

``data/demo-site/site.json`` records the site's parcels, extent and source
layers, verified against the live LINZ and Buller services (see issue #4).
``load_demo_site`` reads it and checks its own claims, so a bad edit fails
loudly instead of placing a design on the wrong land.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from button_nz.geo.tiles import tile_bounds

DEMO_SITE_DIR = Path(__file__).resolve().parents[2] / "data" / "demo-site"

type Point = tuple[float, float]
type BBox = tuple[float, float, float, float]
type Ring = tuple[Point, ...]


@dataclass(frozen=True)
class Capture:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class RasterSource:
    title: str
    collection: str
    tile: str
    asset: str
    resolution_m: float
    capture: Capture
    licence: str
    attribution: str


@dataclass(frozen=True)
class VectorSource:
    title: str
    service: str
    licence: str
    attribution: str
    capture: Capture | None


@dataclass(frozen=True)
class Parcel:
    parcel_id: int
    appellation: str
    survey_area_m2: float
    ring: Ring


@dataclass(frozen=True)
class DemoSite:
    name: str
    title: str
    valuation_number: str
    address_nztm: Point
    parcels: tuple[Parcel, ...]
    extent_nztm: BBox
    rasters: Mapping[str, RasterSource]
    vectors: Mapping[str, VectorSource]
    open_items: tuple[str, ...]


def contains(ring: Ring, point: Point) -> bool:
    """Whether ``point`` lies inside the closed polygon ``ring`` (ray casting)."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def load_demo_site(directory: Path = DEMO_SITE_DIR) -> DemoSite:
    """Load and check the demo-site manifest in ``directory``."""
    manifest = _read(directory / "site.json")
    parcels = _parcels(_read(directory / str(manifest["parcels_file"])))
    site = DemoSite(
        name=str(manifest["name"]),
        title=str(manifest["title"]),
        valuation_number=str(manifest["valuation_number"]),
        address_nztm=_point(manifest["address"]["nztm"]),
        parcels=parcels,
        extent_nztm=_bbox(manifest["extent"]["nztm"]),
        rasters={k: _raster(v) for k, v in manifest["rasters"].items()},
        vectors={k: _vector(v) for k, v in manifest["vectors"].items()},
        open_items=tuple(str(item) for item in manifest["open_items"]),
    )
    _check(site, [int(i) for i in manifest["parcel_ids"]])
    return site


def _check(site: DemoSite, parcel_ids: Sequence[int]) -> None:
    if [p.parcel_id for p in site.parcels] != list(parcel_ids):
        raise ValueError("parcel_ids do not match the parcels file")
    if site.extent_nztm != _bounds([pt for p in site.parcels for pt in p.ring]):
        raise ValueError("extent.nztm is not the bounding box of the parcels")
    if not any(contains(p.ring, site.address_nztm) for p in site.parcels):
        raise ValueError("the address point is not inside any parcel")
    captures = {k: r.capture for k, r in site.rasters.items()}
    captures |= {k: v.capture for k, v in site.vectors.items() if v.capture}
    for key, capture in captures.items():
        if capture.start > capture.end:
            raise ValueError(f"{key}: capture ends before it starts")
    for key, raster in site.rasters.items():
        if raster.asset != f"{raster.collection.rsplit('/', 1)[0]}/{raster.tile}.tiff":
            raise ValueError(f"{key}: asset is not tile {raster.tile} in its collection")
        if not _covers(tile_bounds(raster.tile), site.extent_nztm):
            raise ValueError(f"{key}: tile {raster.tile} does not cover the site")


def _read(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _parcels(geojson: Mapping[str, Any]) -> tuple[Parcel, ...]:
    return tuple(
        Parcel(
            parcel_id=int(f["properties"]["parcel_id"]),
            appellation=str(f["properties"]["appellation"]),
            survey_area_m2=float(f["properties"]["survey_area_m2"]),
            ring=tuple(_point(pt) for pt in f["geometry"]["coordinates"][0]),
        )
        for f in geojson["features"]
    )


def _raster(raw: Mapping[str, Any]) -> RasterSource:
    return RasterSource(
        title=str(raw["title"]),
        collection=str(raw["collection"]),
        tile=str(raw["tile"]),
        asset=str(raw["asset"]),
        resolution_m=float(raw["resolution_m"]),
        capture=_capture(raw["capture"]),
        licence=str(raw["licence"]),
        attribution=str(raw["attribution"]),
    )


def _vector(raw: Mapping[str, Any]) -> VectorSource:
    return VectorSource(
        title=str(raw["title"]),
        service=str(raw["service"]),
        licence=str(raw["licence"]),
        attribution=str(raw["attribution"]),
        capture=_capture(raw["capture"]) if "capture" in raw else None,
    )


def _capture(raw: Mapping[str, str]) -> Capture:
    return Capture(datetime.fromisoformat(raw["start"]), datetime.fromisoformat(raw["end"]))


def _point(raw: Sequence[float]) -> Point:
    return (float(raw[0]), float(raw[1]))


def _bbox(raw: Sequence[float]) -> BBox:
    return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))


def _bounds(points: Sequence[Point]) -> BBox:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _covers(outer: BBox, inner: BBox) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )
