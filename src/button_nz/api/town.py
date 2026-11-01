"""The town screen as a map layer, and the aerial basemap, over HTTP.

    GET /town/{slug}                       every screened section, coloured
    GET /tiles/aerial/{z}/{x}/{y}.webp     LINZ Basemaps' aerial, through this server

A town's sections come from its screen's ``results.jsonl`` (``bench.town_screen``)
and their outlines from LINZ's NZ Primary Parcels (CC BY 4.0) by the same ids,
read once and kept; a section LINZ has no parcel for is listed in ``missing``,
never drawn from another source. Each section's ``category`` is the screen's with 0.6 m
eaves: ``clear`` if a real prefab fits clear of everything over 2 m on the
LiDAR, ``outlines`` if one fits only judged against LINZ's building outlines,
else ``none``. Under ``buildings``, each LINZ building outline touching a
screened section has its ``height_m`` above the ground: the 90th percentile of
the nDSM from the LiDAR tiles the screen read (null where no cell's centre
falls inside it). The town map has no terrain, so heights count from the ground.

Tiles are fetched with the server's ``LINZ_BASEMAP_API_KEY``, which never
leaves it; only real WebMercatorQuad tiles are asked for.
"""

import hashlib
import json
import math
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import APIRouter, HTTPException, Response
from shapely import STRtree, union_all
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from button_nz.geo.arcgis import ArcGISError, FeatureLayer
from button_nz.geo.geometry import BBox
from button_nz.geo.lonlat import lonlat
from button_nz.geo.terrain import TerrainGrid
from button_nz.sites.heights import height_above

RESULTS = Path(__file__).resolve().parents[3] / "docs" / "results" / "town-screen" / "results.jsonl"
TOWNS = {"reefton": RESULTS}
LINZ_PRIMARY_PARCELS = (
    "https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/"
    "LINZ_NZ_Primary_Parcels/FeatureServer/0"
)
BATCH = 100  # ids per parcels query
MAX_ZOOM = 22
MISSING = "not in LINZ's NZ Primary Parcels"
ONE_DAY_S = 86400

type Outlines = Callable[[BBox], dict[str, Any]]  # LINZ building outlines (NZTM GeoJSON)
type TownLidar = Callable[[BBox], TerrainGrid]  # the DEM and nDSM over a whole-metre bbox


def category(row: Mapping[str, Any]) -> str:
    if row.get("clear_eaves"):
        return "clear"
    return "outlines" if row.get("fits_eaves") else "none"


# The layer's format, in its cache key: bump it whenever ``_build``'s output
# changes, so a layer cached in an older format is rebuilt, never served.
LAYER_FORMAT = 3


RANK = {"none": 0, "outlines": 1, "clear": 2}


def _property_categories(rows: Sequence[Mapping[str, Any]]) -> dict[int, str]:
    """Each property's category: the best of its parcels', so every parcel of
    a title is coloured by what the property has room for."""
    best: dict[int, str] = {}
    for row in rows:
        pid, found = int(row["property_id"]), category(row)
        if RANK[found] > RANK[best.get(pid, "none")]:
            best[pid] = found
        best.setdefault(pid, found)
    return best


class TownMaps:
    def __init__(
        self,
        towns: Mapping[str, Path],
        parcels: FeatureLayer,
        cache: Path,
        outlines: Outlines,
        lidar: TownLidar,
    ) -> None:
        self.towns, self.parcels, self.cache = towns, parcels, cache
        self.outlines, self.lidar = outlines, lidar
        self._lock = threading.Lock()

    def layer(self, slug: str) -> dict[str, Any]:
        """The town's sections, coloured, in lon/lat. The layer is kept under the
        hash of the screen's results, so new results are never coloured by an
        old layer."""
        results = self.towns[slug]
        version = hashlib.sha256(results.read_bytes()).hexdigest()[:12]
        path = self.cache / f"{slug}-{version}-v{LAYER_FORMAT}.geojson"
        with self._lock:
            if not path.is_file():
                self.cache.mkdir(parents=True, exist_ok=True)
                layer = json.dumps(self._build(results))
                partial = path.with_suffix(".partial")  # a cut-off write never looks whole
                partial.write_text(layer, encoding="utf-8")
                partial.replace(path)
        found: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return found

    def _build(self, results: Path) -> dict[str, Any]:
        rows = [
            json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line
        ]
        ids = [int(r["parcel_id"]) for r in rows]
        outlines: dict[int, Any] = {}
        for start in range(0, len(ids), BATCH):
            batch = ",".join(str(i) for i in ids[start : start + BATCH])
            for feature in self.parcels.where(f"id IN ({batch})").features:
                props = cast("dict[str, Any]", feature["properties"])
                outlines[int(props["id"])] = shape(cast("dict[str, Any]", feature["geometry"]))
        best = _property_categories(rows)
        features = [
            {
                "type": "Feature",
                "properties": {
                    "id": int(r["parcel_id"]),
                    "property": int(r["property_id"]),
                    "category": best[int(r["property_id"])],
                },
                "geometry": mapping(lonlat(outlines[int(r["parcel_id"])])),
            }
            for r in rows
            if int(r["parcel_id"]) in outlines
        ]
        missing = {"ids": [i for i in ids if i not in outlines], "reason": MISSING}
        buildings = self._buildings(list(outlines.values()))
        return {
            "type": "FeatureCollection",
            "features": features,
            "missing": missing,
            "buildings": buildings,
        }

    def _buildings(self, sections: list[BaseGeometry]) -> dict[str, Any]:
        """The LINZ outlines touching ``sections``, each standing on its own
        ground: ``base_m`` 0 and ``height_m`` its top, as on a site map."""
        if not sections:  # nothing to ask outlines over
            return {"type": "FeatureCollection", "features": []}
        tree = STRtree(sections)
        found = self.outlines(_bounds(sections))["features"]
        on = [
            (f, g)
            for f in found
            for g in (shape(f["geometry"]),)
            if len(tree.query(g, predicate="intersects"))
        ]
        if not on:
            return {"type": "FeatureCollection", "features": []}
        grid = self.lidar(_whole_metres(_bounds([g for _, g in on])))
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": f.get("id"),
                    "properties": _on_own_ground(_rounded(height_above(grid, g))),
                    "geometry": mapping(lonlat(g)),
                }
                for f, g in on
            ],
        }


def _on_own_ground(above: float | None) -> dict[str, float | None]:
    """A town building's extrusion: no site datum, so its own ground is 0."""
    if above is None:
        return {"base_m": None, "height_m": None, "above_ground_m": None}
    return {"base_m": 0.0, "height_m": above, "above_ground_m": above}


def _bounds(geometries: list[BaseGeometry]) -> BBox:
    x0, y0, x1, y1 = union_all(geometries).bounds
    return (x0, y0, x1, y1)


def _whole_metres(bbox: BBox) -> BBox:
    """``bbox`` widened to whole metres: the LiDAR's grid."""
    x0, y0, x1, y1 = bbox
    return (
        float(math.floor(x0)),
        float(math.floor(y0)),
        float(math.ceil(x1)),
        float(math.ceil(y1)),
    )


def _rounded(height: float | None) -> float | None:
    return None if height is None else round(height, 2)


def town_router(maps: TownMaps) -> APIRouter:
    router = APIRouter()

    @router.get("/town/{slug}")
    def get_town(slug: str) -> dict[str, Any]:
        if slug not in maps.towns:
            raise HTTPException(404, f"no town screen for {slug}")
        try:
            return maps.layer(slug)
        except ArcGISError as error:
            raise HTTPException(502, f"LINZ's parcels failed: {error}") from None

    return router


def tiles_router(client: httpx.Client, key: Callable[[], str | None], base: str) -> APIRouter:
    router = APIRouter()

    @router.get("/tiles/aerial/{z}/{x}/{y}.webp")
    def get_tile(z: int, x: int, y: int) -> Response:
        if not 0 <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
            raise HTTPException(404, f"no aerial tile {z}/{x}/{y}")
        api_key = key()
        if not api_key:
            raise HTTPException(503, "the aerial basemap needs LINZ_BASEMAP_API_KEY on the server")
        url = f"{base}/aerial/WebMercatorQuad/{z}/{x}/{y}.webp"
        try:
            upstream = client.get(url, params={"api": api_key})
        except httpx.HTTPError:
            raise HTTPException(502, "LINZ Basemaps didn't answer") from None
        if upstream.status_code != 200:
            raise HTTPException(upstream.status_code if upstream.status_code == 404 else 502)
        return Response(
            upstream.content,
            media_type="image/webp",
            headers={"Cache-Control": f"public, max-age={ONE_DAY_S}"},
        )

    return router
