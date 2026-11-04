"""A site's build as it goes (#152): what each step has found so far.

    GET /sites/{id}/progress                 ``sites.progress.read_progress``, with
                                             each image's URL beside its bbox
    GET /sites/{id}/progress/{layer}.png     the terrain preview, or the aerial

Both answer while the site is still building, and after: the images are
read from the site's directory as the build leaves them.
"""

import json
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Response

from button_nz.sites.progress import TERRAIN_PREVIEW, read_progress

if TYPE_CHECKING:
    from button_nz.api.sites import Sites

type Layer = Literal["terrain", "aerial"]
FILES: dict[str, str] = {"terrain": TERRAIN_PREVIEW, "aerial": "aerial.png"}
FRESH = {"Cache-Control": "no-store"}  # it changes with every step


def progress_router(sites: Sites) -> APIRouter:
    router = APIRouter()

    @router.get("/sites/{site_id}/progress")
    def get_progress(site_id: str) -> Response:
        sites.record(site_id)  # a 404 for a site there isn't
        shown: dict[str, Any] = read_progress(sites.sites_dir / site_id)
        for layer in FILES:
            if shown[layer] is not None:
                shown[layer] = shown[layer] | {"url": f"/sites/{site_id}/progress/{layer}.png"}
        return Response(json.dumps(shown), media_type="application/json", headers=FRESH)

    @router.get("/sites/{site_id}/progress/{layer}.png")
    def get_layer(site_id: str, layer: Layer) -> Response:
        sites.record(site_id)
        path = sites.sites_dir / site_id / FILES[layer]
        if read_progress(sites.sites_dir / site_id)[layer] is None or not path.is_file():
            raise HTTPException(404, f"site {site_id} has no {layer} to show yet")
        return Response(path.read_bytes(), media_type="image/png", headers=FRESH)

    return router
