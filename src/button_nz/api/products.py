"""The real prefab products that fit inside an accepted design.

    GET /designs/{id}/products    {footprint_m2, fits, unchecked, basis}

The footprint is the walls Blender measured of the accepted attempt
(``measurements.json``), as the evaluator saw them.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from shapely import Polygon

from button_nz.agent.proposal import DesignError, parse_measurements
from button_nz.api.store import Store
from button_nz.catalogue import Product, matches

BASIS = (
    "A product fits if its published outside footprint lies inside the accepted "
    "design's walls, square to one of them, so it keeps the design's boundary, "
    "separation and kept-area checks. Its height and floor level are not checked: "
    "the suppliers' figures don't include them. Products whose published dimensions "
    "aren't labelled can't be checked."
)


class ProductsView(BaseModel):
    footprint_m2: float
    fits: list[Product]  # largest first
    unchecked: list[Product]
    basis: str


def products_router(store: Store, runs_dir: Path, products: Sequence[Product]) -> APIRouter:
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
        return ProductsView(
            footprint_m2=round(walls.area, 2),
            fits=list(found.fits),
            unchecked=list(found.unchecked),
            basis=BASIS,
        )

    return router


def _walls(attempt: Path) -> Polygon:
    """The accepted attempt's walls, as measured: an accepted attempt always has them."""
    raw = json.loads((attempt / "measurements.json").read_text(encoding="utf-8"))
    footprint = parse_measurements(raw).footprint
    if footprint is None:
        raise DesignError(f"{attempt} was accepted without a measured footprint")
    return Polygon(footprint)
