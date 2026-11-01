"""A site's map layers, as GeoJSON in EPSG:4326 (RFC 7946) for a web map.

The rules are drawn with the evaluator's own numbers, so the map shows what
designs are checked against:

- ``setback``: the band within ``MIN_SEPARATION_M`` of the title boundary;
- ``halos``: the band within ``MIN_SEPARATION_M`` of each confirmed building;
- ``keep_clear``: what the owner keeps clear;
- ``room``: where a dwelling's outline may stand: the title less its setback,
  the confirmed buildings and their halos, and the keep-clear areas.

Lines between parcels on one title aren't taken out of ``room``: whether they
are legal boundaries is unknown, and the evaluator reports them so.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from shapely import MultiPolygon, Polygon, union_all
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from button_nz.demo_site import DemoSite
from button_nz.evaluation.checks import MIN_SEPARATION_M
from button_nz.geo.geometry import BBox
from button_nz.geo.lonlat import TO_LONLAT, lonlat
from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.confirm import Survey
from button_nz.sites.heights import canopy, height_above, median_ground

_DIGITS = 7  # about 1 cm


def lonlat_bounds(bbox: BBox) -> list[float]:
    """``bbox`` (NZTM) as [west, south, east, north] in lon/lat."""
    west, south, east, north = TO_LONLAT.transform_bounds(*bbox)
    return [round(v, _DIGITS) for v in (west, south, east, north)]


def collection(items: Iterable[tuple[BaseGeometry, Mapping[str, Any]]]) -> dict[str, Any]:
    """A FeatureCollection of (NZTM geometry, properties), in lon/lat."""
    features = [
        {"type": "Feature", "properties": dict(props), "geometry": _rounded(mapping(lonlat(g)))}
        for g, props in items
        if not g.is_empty
    ]
    return {"type": "FeatureCollection", "features": features}


@dataclass(frozen=True)
class Lidar:
    """The site's LiDAR grid, and its datum: heights are given above the datum."""

    grid: TerrainGrid
    datum_m: float


def site_layers(
    site: DemoSite,
    survey: Survey | None,
    decisions: Mapping[str, str],
    buildings: Mapping[str, Any],
    lidar: Lidar | None = None,
) -> dict[str, dict[str, Any]]:
    """Every layer of ``site``, its ``survey`` with ``decisions``, and the LINZ
    ``buildings`` outlines (an NZTM FeatureCollection). With ``lidar``, each
    building gains ``height_m`` (nDSM p90) and ``base_m`` (median ground above
    the datum), each survey feature ``height_m``, and ``canopy`` what stands
    over 2 m outside the buildings."""
    found = [] if survey is None else cast("list[dict[str, Any]]", survey.collection["features"])
    decided = [(shape(f["geometry"]), str(f["id"]), decisions.get(str(f["id"]))) for f in found]
    confirmed = [g for g, _, d in decided if d == "building"]
    kept = [g for g, _, d in decided if d == "keep_clear"]
    title = union_all([Polygon(p.ring) for p in site.parcels])
    inner = title.buffer(-MIN_SEPARATION_M)
    built = union_all(confirmed) if confirmed else Polygon()
    grown = built.buffer(MIN_SEPARATION_M) if confirmed else Polygon()
    clear = union_all(kept) if kept else Polygon()
    rule = {"metres": MIN_SEPARATION_M}
    return {
        "parcels": collection(
            (Polygon(p.ring), {"id": p.parcel_id, "appellation": p.appellation})
            for p in site.parcels
        ),
        "buildings": collection(
            (g, {"id": f.get("id"), **_building_heights(g, lidar)})
            for f in buildings.get("features", [])
            for g in (shape(f["geometry"]),)
        ),
        "features": collection(
            (g, {**f["properties"], "id": str(f["id"]), "decision": d, **_height(g, lidar)})
            for f, (g, _, d) in zip(found, decided, strict=True)
        ),
        "canopy": _canopy(buildings, lidar),
        "setback": collection([(title.difference(inner), rule)]),
        "halos": collection([(grown.difference(built), rule)]),
        "keep_clear": collection((g, {"id": i}) for g, i, d in decided if d == "keep_clear"),
        "room": collection([(_polygonal(inner.difference(grown).difference(clear)), {})]),
    }


def _height(geometry: BaseGeometry, lidar: Lidar | None) -> dict[str, float]:
    found = None if lidar is None else height_above(lidar.grid, geometry)
    return {} if found is None else {"height_m": round(found, 2)}


def _building_heights(geometry: BaseGeometry, lidar: Lidar | None) -> dict[str, float]:
    ground = None if lidar is None else median_ground(lidar.grid, geometry)
    base = {} if ground is None or lidar is None else {"base_m": round(ground - lidar.datum_m, 2)}
    return _height(geometry, lidar) | base


def _canopy(buildings: Mapping[str, Any], lidar: Lidar | None) -> dict[str, Any]:
    if lidar is None:
        return collection([])
    outlines = [shape(f["geometry"]) for f in buildings.get("features", [])]
    trees = canopy(lidar.grid, outlines)
    return collection((tree, {"height_m": round(height, 2)}) for tree, height in trees)


def _polygonal(geometry: BaseGeometry) -> BaseGeometry:
    """Only the areas of ``geometry``: a difference can leave slivers of line."""
    if isinstance(geometry, Polygon | MultiPolygon):
        return geometry
    parts: Sequence[BaseGeometry] = getattr(geometry, "geoms", [])
    return union_all([p for p in parts if isinstance(p, Polygon | MultiPolygon)])


def _rounded(geometry: Mapping[str, Any]) -> dict[str, Any]:
    def walk(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, _DIGITS)
        if isinstance(value, list | tuple):
            return [walk(v) for v in cast("Sequence[Any]", value)]
        return value

    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}
