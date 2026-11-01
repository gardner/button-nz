"""The real prefab products that fit inside an accepted design.

    GET /designs/{id}/products    {footprint_m2, fits, unchecked, basis}

The footprint is the walls Blender measured of the accepted attempt
(``measurements.json``), as the evaluator saw them.
"""

import json
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from shapely import Polygon
from shapely.affinity import translate

from button_nz.agent.proposal import DesignError, parse_measurements
from button_nz.api.store import Job, Store
from button_nz.catalogue import Product, matches, placement
from button_nz.geo.crs import LocalFrame
from button_nz.sites.layers import collection

BASIS = (
    "A product fits if its published outside wall footprint lies inside the accepted "
    "design's walls, square to one of them. It keeps the design's boundary, separation "
    "and kept-area verdicts only if its eaves overhang no further than the design's, "
    "and the suppliers mostly don't publish eaves: those checks need running on the "
    "product's own outline. Its height and floor level are not checked either. Products "
    "whose published dimensions aren't labelled can't be checked."
)


class ProductsView(BaseModel):
    footprint_m2: float
    fits: list[dict[str, Any]]  # largest first; each with where it would stand
    unchecked: list[Product]
    basis: str


type FrameFor = Callable[[Job], LocalFrame]  # the frame a job's designs are measured in


def products_router(
    store: Store, runs_dir: Path, products: Sequence[Product], frame_for: FrameFor | None = None
) -> APIRouter:
    """With ``frame_for``, each fitting product says where it would stand inside
    the walls (``placed_footprint``, lon/lat)."""
    router = APIRouter()

    @router.get("/designs/{job_id}/products")
    def get_products(job_id: str) -> ProductsView:
        try:
            job = store.get_job(job_id)
        except KeyError:
            raise HTTPException(404, f"no design {job_id}") from None
        if job.accepted_attempt is None:
            raise HTTPException(409, f"design {job_id} has no accepted attempt")
        walls = _walls(runs_dir / job.id / f"attempt-{job.accepted_attempt}")
        found = matches(walls, products)
        frame = None if frame_for is None else frame_for(job)
        return ProductsView(
            footprint_m2=round(walls.area, 2),
            fits=[_fitting(p, walls, frame) for p in found.fits],
            unchecked=list(found.unchecked),
            basis=BASIS,
        )

    return router


def _fitting(product: Product, walls: Polygon, frame: LocalFrame | None) -> dict[str, Any]:
    view = product.model_dump()
    if frame is None:
        return view
    placed = placement(walls, product.length_m, product.width_m)
    if placed is None:  # matches() found it fits: placement() is the same test
        raise ValueError(f"{product.id} fits but has no placement")
    on_site = translate(placed, frame.origin[0], frame.origin[1])
    return view | {"placed_footprint": collection([(on_site, {"id": product.id})])}


@lru_cache(maxsize=64)
def _walls(attempt: Path) -> Polygon:
    """The accepted attempt's walls, as measured: an accepted attempt always has them,
    and never changes, so they are measured once."""
    raw = json.loads((attempt / "measurements.json").read_text(encoding="utf-8"))
    footprint = parse_measurements(raw).footprint
    if footprint is None:
        raise DesignError(f"{attempt} was accepted without a measured footprint")
    return Polygon(footprint)
