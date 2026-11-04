"""The real prefab products that fit inside an accepted design.

    GET /products                 the catalogue, to browse
    GET /designs/{id}/products    {footprint_m2, fits, unchecked, basis}

The footprint is the walls Blender measured of the accepted attempt
(``measurements.json``), as the evaluator saw them. A fitting product that
neither its pose inside those walls nor the placement search
(``agent.placement``) could stand with its floor level passing keeps its
place in the fits, with a ``floor_level_note`` saying what was measured: the
search samples poses, so it proves nothing.
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

from button_nz.agent.placement import least_ground_range
from button_nz.agent.proposal import DesignError, parse_measurements
from button_nz.agent.site import DesignSite
from button_nz.api.store import Job, Store
from button_nz.catalogue import Product, matches, placement
from button_nz.evaluation import InvalidProposal, SiteContext, checks
from button_nz.evaluation.checks import MAX_FLOOR_ABOVE_GROUND_M
from button_nz.geo.crs import LocalFrame
from button_nz.sites.layers import collection

BASIS = (
    "A product fits if its published outside wall footprint lies inside the accepted "
    "design's walls, square to one of them. It keeps the design's boundary, separation "
    "and kept-area verdicts only if its eaves overhang no further than the design's, "
    "and the suppliers mostly don't publish eaves: those checks need running on the "
    "product's own outline. Its height is not checked either. Its floor level (at most "
    "1 m above the lowest ground under it) is checked where it stands inside the walls "
    "and at the positions a search of the site tries; where none passes, a note says "
    "what was measured. Products whose published dimensions aren't labelled can't be "
    "checked."
)


class ProductsView(BaseModel):
    footprint_m2: float
    fits: list[dict[str, Any]]  # largest first; each with where it would stand
    unchecked: list[Product]
    basis: str


FIT_STEP_DEG = 5.0  # the search turns a product this finely

type FrameFor = Callable[[Path], LocalFrame]  # the frame an attempt was measured in
type SiteFor = Callable[[Job], DesignSite]  # the site a product placed after a job stands on


def products_router(
    store: Store,
    runs_dir: Path,
    products: Sequence[Product],
    frame_for: FrameFor | None = None,
    site_for: SiteFor | None = None,
) -> APIRouter:
    """With ``frame_for``, each fitting product says where it would stand inside
    the walls (``placed_footprint``, lon/lat): wholly inside where it has room,
    else over each wall by half of ``catalogue.fit.TOLERANCE_M`` at most. With
    ``site_for``, a product that fits the walls but can't stand anywhere on the
    site within the floor-level rule says so (``floor_level_note``)."""
    router = APIRouter()

    @router.get("/products")
    def get_catalogue() -> list[Product]:
        """Every product in the catalogue, as catalogued: to browse while a
        design is made, before there are walls to fit."""
        return list(products)

    @router.get("/designs/{job_id}/products")
    def get_products(job_id: str) -> ProductsView:
        try:
            job = store.get_job(job_id)
        except KeyError:
            raise HTTPException(404, f"no design {job_id}") from None
        if job.accepted_attempt is None:
            raise HTTPException(409, f"design {job_id} has no accepted attempt")
        attempt = runs_dir / job.id / f"attempt-{job.accepted_attempt}"
        walls = _walls(attempt)
        found = matches(walls, products)
        frame = None if frame_for is None else frame_for(attempt)
        site = None if site_for is None else site_for(job).context
        return ProductsView(
            footprint_m2=round(walls.area, 2),
            fits=[
                _fitting(p, walls, frame) | {"floor_level_note": _floor_note(p, walls, frame, site)}
                for p in found.fits
            ],
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


def _floor_note(
    product: Product, walls: Polygon, frame: LocalFrame | None, site: SiteContext | None
) -> str | None:
    """What was measured, when neither ``product``'s pose inside the design's
    ``walls`` nor any pose the search tried on ``site`` passes floor level (on
    the most lenient reading: no eaves, a section line only not crossed);
    None if one passes, or the site isn't known."""
    if site is None:
        return None
    inside = _range_inside(product, walls, frame, site)
    if inside is not None and inside <= MAX_FLOOR_ABOVE_GROUND_M:
        return None
    least = least_ground_range(
        site, product.length_m, product.width_m, section_clear_m=0.0, angle_step_deg=FIT_STEP_DEG
    )
    if least is None or least <= MAX_FLOOR_ABOVE_GROUND_M:
        return None  # floor level can pass somewhere, or something else stops it
    measured = "the ground under it varies "
    if inside is not None:
        measured = f"inside the design's walls {measured}by {inside:.2f} m; "
    return (
        f"May need earthworks: {measured}at every position the search tried on the site "
        f"(turned every {FIT_STEP_DEG:g}°), by at least {least:.2f} m. The floor may stand "
        f"at most {MAX_FLOOR_ABOVE_GROUND_M:g} m above the lowest ground; the search samples "
        "positions, so one it didn't try may pass."
    )


def _range_inside(
    product: Product, walls: Polygon, frame: LocalFrame | None, site: SiteContext
) -> float | None:
    """The evaluator's ground range under ``product`` where it stands inside
    the design's ``walls``; None if that can't be measured on ``site``'s
    terrain (no frame, or walls measured in a frame it doesn't cover)."""
    inside = placement(walls, product.length_m, product.width_m)
    if inside is None or frame is None:
        return None
    on_site = translate(inside, frame.origin[0], frame.origin[1])
    try:
        lowest, highest = checks.ground_range(on_site, site.terrain)
    except InvalidProposal:
        return None
    return highest - lowest


@lru_cache(maxsize=64)
def _walls(attempt: Path) -> Polygon:
    """The accepted attempt's walls, as measured: an accepted attempt always has them,
    and never changes, so they are measured once."""
    raw = json.loads((attempt / "measurements.json").read_text(encoding="utf-8"))
    walls = parse_measurements(raw).walls()  # an open courtyard is no room for a product
    if walls is None:
        raise DesignError(f"{attempt} was accepted without a measured footprint")
    return walls
