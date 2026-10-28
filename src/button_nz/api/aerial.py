"""The site's aerial photograph, for the web app to draw under its plan.

    GET /site/aerial.png    the photo over ``bbox`` (given in ``/site``), north up

It is read from the source tiles the first time it is asked for and then kept,
so serving the site doesn't wait on the imagery.
"""

import io
import math
import threading
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Response
from PIL import Image

from button_nz.demo_site import DemoSite
from button_nz.geo.geometry import BBox

AERIAL_MARGIN_M = 10.0  # beyond the site, so trees and sheds on its edge show whole
AERIAL_PIXEL_M = 0.125


class SiteAerial:
    """The photo over ``bbox``, made by ``render`` (PNG bytes) once, when first used."""

    def __init__(self, bbox: BBox, render: Callable[[], bytes]) -> None:
        self.bbox = bbox
        self._render = render
        self._png: bytes | None = None
        self._lock = threading.Lock()

    def png(self) -> bytes:
        with self._lock:
            if self._png is None:
                self._png = self._render()
            return self._png


def aerial_bbox(site: DemoSite, margin_m: float = AERIAL_MARGIN_M) -> BBox:
    """The site's extent and ``margin_m`` around it, out to whole metres."""
    west, south, east, north = site.extent_nztm
    return (
        float(math.floor(west - margin_m)),
        float(math.floor(south - margin_m)),
        float(math.ceil(east + margin_m)),
        float(math.ceil(north + margin_m)),
    )


def demo_aerial(site: DemoSite) -> SiteAerial:
    """The demo site's urban aerial, read when first asked for."""
    bbox = aerial_bbox(site)

    def render() -> bytes:
        from button_nz.agent.demo import aerial_of  # reads imagery: only when needed

        buffer = io.BytesIO()
        Image.fromarray(aerial_of(bbox, AERIAL_PIXEL_M), "RGB").save(buffer, format="PNG")
        return buffer.getvalue()

    return SiteAerial(bbox, render)


def aerial_view(aerial: SiteAerial | None) -> dict[str, object] | None:
    """Where the aerial is, for ``/site``: None if there isn't one."""
    return None if aerial is None else {"bbox": list(aerial.bbox), "url": "/site/aerial.png"}


def aerial_router(aerial: SiteAerial | None) -> APIRouter:
    router = APIRouter()

    @router.get("/site/aerial.png")
    def get_aerial() -> Response:
        if aerial is None:
            raise HTTPException(404, "no aerial photograph for this site")
        return Response(aerial.png(), media_type="image/png")

    return router
