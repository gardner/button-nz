"""The verified demo site: 35 Victory Street, Reefton.

``data/demo-site/site.json`` records the site's parcels, extent and source
layers, verified against the live LINZ and Buller services (see issue #4).
``load_demo_site`` reads it and checks its own claims, so a bad edit fails
loudly instead of placing a design on the wrong land.

A site built for any address (``button_nz.sites``) has a manifest of the same
shape, except that each raster lists the LINZ ``tiles`` it was joined from and
its ``asset`` is the joined file beside the manifest; it has no valuation
number, which only Buller's rating data gives.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from shapely import Point as ShapelyPoint
from shapely import Polygon, union_all
from shapely.geometry.base import BaseGeometry

from button_nz.geo.geometry import BBox, Point, Ring, bounds, contains, covers
from button_nz.geo.tiles import tile_bounds

__all__ = ["DEMO_SITE_DIR", "DemoSite", "contains", "load_demo_site"]

DEMO_SITE_DIR = Path(__file__).resolve().parents[2] / "data" / "demo-site"


@dataclass(frozen=True)
class Capture:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class RasterSource:
    title: str
    collection: str
    tile: str | None  # the one LINZ tile, or None for a raster joined from ``tiles``
    asset: str  # what to read: the tile's URL, or the joined local file
    resolution_m: float
    capture: Capture
    licence: str
    attribution: str
    tiles: tuple[str, ...] = ()  # the LINZ tiles it was joined from


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
    valuation_number: str | None  # Buller's rating data only
    address_nztm: Point
    parcels: tuple[Parcel, ...]
    extent_nztm: BBox
    rasters: Mapping[str, RasterSource]
    vectors: Mapping[str, VectorSource]
    open_items: tuple[str, ...]


def load_demo_site(directory: Path = DEMO_SITE_DIR) -> DemoSite:
    """Load and check the demo-site manifest in ``directory``."""
    manifest = _read(directory / "site.json")
    parcels = _parcels(_read(directory / str(manifest["parcels_file"])))
    site = DemoSite(
        name=str(manifest["name"]),
        title=str(manifest["title"]),
        valuation_number=_optional(manifest["valuation_number"]),
        address_nztm=_point(manifest["address"]["nztm"]),
        parcels=parcels,
        extent_nztm=_bbox(manifest["extent"]["nztm"]),
        rasters={k: _raster(v, directory) for k, v in manifest["rasters"].items()},
        vectors={k: _vector(v) for k, v in manifest["vectors"].items()},
        open_items=tuple(str(item) for item in manifest["open_items"]),
    )
    _check(site, [int(i) for i in manifest["parcel_ids"]])
    return site


def _check(site: DemoSite, parcel_ids: Sequence[int]) -> None:
    if [p.parcel_id for p in site.parcels] != list(parcel_ids):
        raise ValueError("parcel_ids do not match the parcels file")
    if site.extent_nztm != bounds([pt for p in site.parcels for pt in p.ring]):
        raise ValueError("extent.nztm is not the bounding box of the parcels")
    if not any(_on(p.ring, site.address_nztm) for p in site.parcels):
        raise ValueError("the address point is not inside any parcel")
    captures = {k: r.capture for k, r in site.rasters.items()}
    captures |= {k: v.capture for k, v in site.vectors.items() if v.capture}
    for key, capture in captures.items():
        if capture.start > capture.end:
            raise ValueError(f"{key}: capture ends before it starts")
    for key, raster in site.rasters.items():
        if raster.tile is None:
            _check_joined(key, raster, site.extent_nztm)
            continue
        if raster.asset != f"{raster.collection.rsplit('/', 1)[0]}/{raster.tile}.tiff":
            raise ValueError(f"{key}: asset is not tile {raster.tile} in its collection")
        if not covers(tile_bounds(raster.tile), site.extent_nztm):
            raise ValueError(f"{key}: tile {raster.tile} does not cover the site")


def _on(ring: Ring, point: Point) -> bool:
    """Whether ``point`` is in ``ring`` or on its edge: an address can be on a
    boundary, as the site builder finds its parcel."""
    return Polygon(ring).covers(ShapelyPoint(point))


def _check_joined(key: str, raster: RasterSource, extent: BBox) -> None:
    """A raster joined from tiles: the file is there, and its tiles cover the site."""
    if not Path(raster.asset).is_file():
        raise ValueError(f"{key}: no joined raster at {raster.asset}")
    names = [url.rsplit("/", 1)[1].removesuffix(".tiff") for url in raster.tiles]
    spans = [tile_bounds(name) for name in names]
    if not spans or not covers(_union(spans), extent):
        raise ValueError(f"{key}: its tiles don't cover the site")


def _union(spans: Sequence[BBox]) -> BBox:
    return (
        min(s[0] for s in spans),
        min(s[1] for s in spans),
        max(s[2] for s in spans),
        max(s[3] for s in spans),
    )


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


def _raster(raw: Mapping[str, Any], directory: Path) -> RasterSource:
    joined = "tile" not in raw
    return RasterSource(
        title=str(raw["title"]),
        collection=str(raw["collection"]),
        tile=None if joined else str(raw["tile"]),
        asset=str(directory / str(raw["asset"])) if joined else str(raw["asset"]),
        resolution_m=float(raw["resolution_m"]),
        capture=_capture(raw["capture"]),
        licence=str(raw["licence"]),
        attribution=str(raw["attribution"]),
        tiles=tuple(str(url) for url in raw.get("tiles", ())),
    )


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


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


def site_title(site: DemoSite) -> BaseGeometry:
    """The land on the site's title: its parcels, joined."""
    return union_all([Polygon(parcel.ring) for parcel in site.parcels])
