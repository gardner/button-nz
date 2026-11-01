"""Any address, over HTTP: find it, build a site there, and serve the site.

    GET  /addresses?q=<text>             at most 8 LINZ addresses, in lon/lat
    POST /sites {address_id}             build the site at an address (202); one per address
    GET  /sites/{id}                     its status, step and error; once ready, the site
    GET  /sites/{id}/aerial.png          its aerial photo
    GET  /sites/{id}/map                 its map layers, in lon/lat (``sites.layers``)

and its survey under ``/sites/{id}/features`` (``api.features``). The demo
site is ``DEMO_SITE_ID``, always ready, its survey fixed if the server says so.
"""

import json
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

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
from button_nz.sites.layers import lonlat_bounds, site_layers
from button_nz.sites.registry import DEMO_SITE_ID, SiteBuilder, SiteRecord, SiteStatus, SiteStore
from button_nz.sites.search import QueryError, search_addresses

type Outlines = Callable[[BBox], dict[str, Any]]
"""LINZ building outlines over an NZTM bbox, as a FeatureCollection."""


class SiteRequest(BaseModel):
    address_id: int


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
        if not path.is_file():  # the demo site predates them
            site = self.site(site_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.outlines(aerial_bbox(site))), encoding="utf-8")
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


def sites_router(service: SiteService, store: Store) -> APIRouter:
    sites, addresses = service.sites, service.addresses
    router = APIRouter()

    @router.get("/addresses")
    def get_addresses(q: str = Query(...)) -> dict[str, Any]:
        try:
            return {"addresses": search_addresses(addresses, q)}
        except QueryError as error:
            raise HTTPException(422, str(error)) from None
        except ArcGISError as error:
            raise HTTPException(502, f"LINZ's address search failed: {error}") from None

    @router.post("/sites", status_code=202)
    def post_site(request: SiteRequest) -> dict[str, Any]:
        return _view(sites, _requested(service, request.address_id))

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
        return site_layers(site, survey, decisions, sites.buildings(site_id))

    return router


_REQUESTS = threading.Lock()  # one site per address: requests are decided one at a time


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
        view |= site_view(site) | {
            "bounds": lonlat_bounds(site.extent_nztm),
            "aerial": None
            if aerial is None
            else {"bbox": list(aerial[0]), "url": f"/sites/{record.id}/aerial.png"},
        }
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
