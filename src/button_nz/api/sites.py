"""Any address, over HTTP: find it, build a site there, and serve the site.

    GET  /addresses?q=<text>[&near=lon,lat]  at most 8 LINZ addresses, in lon/lat; near first
    POST /sites {address_id}             build the site at an address (202); one per address
    GET  /sites/{id}                     its status, step and error; once ready, the site
    GET  /sites/{id}/aerial.png          its aerial photo
    GET  /sites/{id}/map                 its map layers, in lon/lat (``sites.layers``)

and its survey under ``/sites/{id}/features`` (``api.features``). The demo
site is ``DEMO_SITE_ID``, always ready, its survey fixed if the server says so.
"""

import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Self

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, model_validator

from button_nz.agent.demo import design_site
from button_nz.agent.loop import DesignSite
from button_nz.api.aerial import SiteAerial, aerial_bbox
from button_nz.api.limits import DailyCap
from button_nz.api.site_view import site_view
from button_nz.api.store import Store
from button_nz.demo_site import DemoSite, load_demo_site
from button_nz.geo.arcgis import ArcGISError, FeatureLayer
from button_nz.geo.geometry import BBox
from button_nz.geo.property import find_address
from button_nz.perception.confirm import Survey
from button_nz.perception.survey import SURVEY_FILE
from button_nz.sites.layers import Lidar, lonlat_bounds, site_layers
from button_nz.sites.registry import DEMO_SITE_ID, SiteBuilder, SiteRecord, SiteStatus, SiteStore
from button_nz.sites.search import (
    NoSuchSection,
    NotASection,
    QueryError,
    address_on_section,
    search_addresses,
)
from button_nz.sites.terrain_tiles import terrain_tile

CACHE_A_DAY = "public, max-age=86400"
DESIGN_SITES_KEPT = 4  # the worker's thread only reads these

type Outlines = Callable[[BBox], dict[str, Any]]
"""LINZ building outlines over an NZTM bbox, as a FeatureCollection."""


class SiteRequest(BaseModel):
    """One of: a LINZ address, or a LINZ primary parcel clicked on the map."""

    address_id: int | None = None
    parcel_id: int | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.address_id is None) == (self.parcel_id is None):
            raise ValueError("name one address_id or one parcel_id")
        return self


class Sites:
    """What a site id means: its record, its manifest, survey, aerial and outlines.

    The demo site's come from the repository and the server's data directory;
    every other site's from its own directory under ``sites_dir``."""

    def __init__(
        self,
        store: SiteStore,
        sites_dir: Path,
        demo: DemoSite,
        demo_survey: Path | None,
        demo_aerial: SiteAerial | None,
        demo_decided_by: str | None,
        outlines: Outlines,
    ) -> None:
        self.store, self.sites_dir, self.outlines = store, sites_dir, outlines
        self.demo, self.demo_survey, self.demo_aerial = demo, demo_survey, demo_aerial
        self.demo_decided_by = demo_decided_by
        self._load = lru_cache(maxsize=64)(load_demo_site)
        self._designs: OrderedDict[str, DesignSite] = OrderedDict()  # the few most recent
        self._outlines_lock = threading.Lock()
        self._designs_lock = threading.Lock()

    def record(self, site_id: str) -> SiteRecord:
        try:
            return self.store.get(site_id)
        except KeyError:
            raise HTTPException(404, f"no site {site_id}") from None

    def site(self, site_id: str) -> DemoSite:
        record = self.record(site_id)
        if record.status is not SiteStatus.READY:
            raise HTTPException(409, f"site {site_id} is {record.status}, not ready")
        return self.demo if site_id == DEMO_SITE_ID else self._load(self.sites_dir / site_id)

    def design_site(self, site_id: str) -> tuple[DesignSite, Path | None]:
        """Where a design on the site is made, and its survey file (``Worker.site_for``)."""
        path, _ = self.survey(site_id)
        with self._designs_lock:  # the worker and the map's requests share it
            if site_id in self._designs:
                self._designs.move_to_end(site_id)
            else:
                self._designs[site_id] = design_site(self.site(site_id))
                while len(self._designs) > DESIGN_SITES_KEPT:  # each holds its terrain grids
                    self._designs.popitem(last=False)
            return self._designs[site_id], path

    def lidar(self, site_id: str) -> Lidar:
        """The site's LiDAR grid and the datum its scene's heights count from."""
        site, _ = self.design_site(site_id)
        return Lidar(site.context.terrain, float(site.scene["frame"]["datum_m"]))

    def survey(self, site_id: str) -> tuple[Path | None, str | None]:
        """The site's survey file, and who fixed it (None: open)."""
        self.site(site_id)
        if site_id == DEMO_SITE_ID:
            return self.demo_survey, self.demo_decided_by
        return self.sites_dir / site_id / SURVEY_FILE, None

    def aerial(self, site_id: str) -> tuple[BBox, Callable[[], bytes]] | None:
        """What the site's photo covers, and its PNG; None if it has none."""
        self.site(site_id)  # ready, or a 404 or 409
        if site_id == DEMO_SITE_ID:
            demo = self.demo_aerial
            return None if demo is None else (demo.bbox, demo.png)
        directory = self.sites_dir / site_id
        raw = json.loads((directory / "site.json").read_text(encoding="utf-8"))["aerial_bbox"]
        bbox = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        return bbox, (directory / "aerial.png").read_bytes

    def buildings(self, site_id: str) -> dict[str, Any]:
        """The LINZ outlines around the site, read once and kept."""
        path = self.sites_dir / site_id / "buildings.geojson"
        with self._outlines_lock:
            if not path.is_file():  # the demo site predates them
                site = self.site(site_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                partial = path.with_suffix(".partial")  # a cut-off write never looks whole
                partial.write_text(json.dumps(self.outlines(aerial_bbox(site))), encoding="utf-8")
                partial.replace(path)
        found: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return found


@dataclass(frozen=True)
class SiteService:
    """Everything the sites routes need: the sites, their builder, LINZ's
    addresses, and the cap on builds a day (None: no cap)."""

    sites: Sites
    builder: SiteBuilder
    addresses: FeatureLayer
    cap: DailyCap | None = None
    parcels: FeatureLayer | None = None  # LINZ NZ Primary Parcels: starting from a section


def sites_router(service: SiteService, store: Store) -> APIRouter:
    sites, addresses = service.sites, service.addresses
    router = APIRouter()

    @router.get("/addresses")
    def get_addresses(
        q: str = Query(...),
        near: str | None = Query(None, description="lon,lat to rank nearby addresses first"),
    ) -> dict[str, Any]:
        try:
            return {"addresses": search_addresses(addresses, q, _lonlat(near))}
        except QueryError as error:
            raise HTTPException(422, str(error)) from None
        except ArcGISError as error:
            raise HTTPException(502, f"LINZ's address search failed: {error}") from None

    @router.post("/sites", status_code=202)
    def post_site(request: SiteRequest) -> dict[str, Any]:
        return _view(sites, _requested(service, _address_of(service, request)))

    @router.get("/sites/{site_id}")
    def get_site(site_id: str) -> dict[str, Any]:
        return _view(sites, sites.record(site_id))

    @router.get("/sites/{site_id}/aerial.png")
    def get_aerial(site_id: str) -> Response:
        found = sites.aerial(site_id)
        if found is None:
            raise HTTPException(404, f"no aerial photograph for site {site_id}")
        return Response(found[1](), media_type="image/png")

    @router.get("/sites/{site_id}/map")
    def get_map(site_id: str) -> dict[str, Any]:
        site = sites.site(site_id)
        path, _ = sites.survey(site_id)
        survey = None if path is None else Survey.read(path)
        decisions = {} if survey is None else store.decisions(survey.id)
        return site_layers(site, survey, decisions, sites.buildings(site_id), sites.lidar(site_id))

    router.include_router(_terrain_router(sites))
    return router


_REQUESTS = threading.Lock()  # one site per address: requests are decided one at a time


def _terrain_router(sites: Sites) -> APIRouter:
    """``GET /sites/{id}/terrain/{z}/{x}/{y}.png``: the site's surface as terrain-RGB."""
    router = APIRouter()

    @router.get("/sites/{site_id}/terrain/{z}/{x}/{y}.png")
    def get_terrain(site_id: str, z: int, x: int, y: int) -> Response:
        lidar = sites.lidar(site_id)
        png = terrain_tile(lidar.grid, lidar.datum_m, z, x, y)
        if png is None:
            raise HTTPException(404, f"no terrain tile {z}/{x}/{y} for site {site_id}")
        return Response(png, media_type="image/png", headers={"Cache-Control": CACHE_A_DAY})

    return router


def _requested(service: SiteService, address_id: int) -> SiteRecord:
    """The site at ``address_id``: the one there is, unless it failed, or a new
    build, within the cap. Two requests for one address get one site."""
    store = service.sites.store
    known = store.by_address(address_id)
    if known is not None and known.status is not SiteStatus.FAILED:
        return known
    address = _address(service.addresses, address_id) if known is None else known.address
    with _REQUESTS:
        known = store.by_address(address_id)  # again: another request may have made it
        if known is not None and known.status is not SiteStatus.FAILED:
            return known
        with _admit(service.cap):
            if known is not None:
                store.rebuild(known.id)
                record = store.get(known.id)
            else:
                record = store.create(address_id, address)
    service.builder.wake()
    return record


def _view(sites: Sites, record: SiteRecord) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": record.id,
        "address": record.address,
        "status": str(record.status),
        "step": record.step,
        "error": record.error,
    }
    if record.status is SiteStatus.READY:
        site = sites.site(record.id)
        aerial = sites.aerial(record.id)
        ready = site_view(site)
        ready["address_nztm"] = ready.pop("address")  # "address" stays the full address
        view = (
            ready
            | view
            | {
                "bounds": lonlat_bounds(site.extent_nztm),
                "aerial": None
                if aerial is None
                else {"bbox": list(aerial[0]), "url": f"/sites/{record.id}/aerial.png"},
            }
        )
    return view


def _address(addresses: FeatureLayer, address_id: int) -> str:
    try:
        return find_address(addresses, address_id).value.full_address
    except LookupError:
        raise HTTPException(404, f"no LINZ address {address_id}") from None
    except ArcGISError as error:
        raise HTTPException(502, f"LINZ's address lookup failed: {error}") from None


def _admit(cap: DailyCap | None) -> AbstractContextManager[None]:
    return nullcontext() if cap is None else cap.admit()


def _lonlat(near: str | None) -> tuple[float, float] | None:
    """``near`` as (lon, lat), or a 422 for anything that isn't a place."""
    if near is None:
        return None
    try:
        lon, lat = (float(v) for v in near.split(","))
    except ValueError:
        raise HTTPException(422, "near is lon,lat") from None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise HTTPException(422, "near is outside the world")
    return lon, lat


def _address_of(service: SiteService, request: SiteRequest) -> int:
    """The address a request names, or the one on the section it names."""
    if request.address_id is not None:
        return request.address_id
    assert request.parcel_id is not None  # the request names one or the other
    if service.parcels is None:
        raise HTTPException(503, "this server can't look up sections; search by address")
    try:
        found = address_on_section(service.addresses, service.parcels, request.parcel_id)
    except NoSuchSection:
        raise HTTPException(404, f"no section {request.parcel_id} in LINZ's parcels") from None
    except NotASection as error:
        raise HTTPException(422, str(error)) from None
    except ArcGISError as error:
        raise HTTPException(502, f"LINZ's parcel lookup failed: {error}") from None
    if found is None:
        raise HTTPException(422, "no address on this section: search for it by its address")
    return found
