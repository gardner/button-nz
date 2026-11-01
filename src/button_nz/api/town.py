"""The town screen as a map layer, and the aerial basemap, over HTTP.

    GET /town/{slug}                       every screened section, coloured
    GET /tiles/aerial/{z}/{x}/{y}.webp     LINZ Basemaps' aerial, through this server

A town's sections come from its screen's ``results.jsonl`` (``bench.town_screen``)
and their outlines from LINZ's NZ Primary Parcels (CC BY 4.0) by the same ids,
read once and kept; a section LINZ has no parcel for is listed in ``missing``,
never drawn from another source. Each section's ``category`` is the screen's with 0.6 m
eaves: ``clear`` if a real prefab fits clear of everything over 2 m on the
LiDAR, ``outlines`` if one fits only judged against LINZ's building outlines,
else ``none``.

Tiles are fetched with the server's ``LINZ_BASEMAP_API_KEY``, which never
leaves it; only real WebMercatorQuad tiles are asked for.
"""

import hashlib
import json
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import APIRouter, HTTPException, Response
from shapely.geometry import mapping, shape

from button_nz.geo.arcgis import ArcGISError, FeatureLayer
from button_nz.geo.lonlat import lonlat

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


def category(row: Mapping[str, Any]) -> str:
    if row.get("clear_eaves"):
        return "clear"
    return "outlines" if row.get("fits_eaves") else "none"


class TownMaps:
    def __init__(self, towns: Mapping[str, Path], parcels: FeatureLayer, cache: Path) -> None:
        self.towns, self.parcels, self.cache = towns, parcels, cache
        self._lock = threading.Lock()

    def layer(self, slug: str) -> dict[str, Any]:
        """The town's sections, coloured, in lon/lat. The layer is kept under the
        hash of the screen's results, so new results are never coloured by an
        old layer."""
        results = self.towns[slug]
        version = hashlib.sha256(results.read_bytes()).hexdigest()[:12]
        path = self.cache / f"{slug}-{version}.geojson"
        with self._lock:
            if not path.is_file():
                self.cache.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(self._build(results)), encoding="utf-8")
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
        features = [
            {
                "type": "Feature",
                "properties": {"id": int(r["parcel_id"]), "category": category(r)},
                "geometry": mapping(lonlat(outlines[int(r["parcel_id"])])),
            }
            for r in rows
            if int(r["parcel_id"]) in outlines
        ]
        missing = {"ids": [i for i in ids if i not in outlines], "reason": MISSING}
        return {"type": "FeatureCollection", "features": features, "missing": missing}


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
