"""The HTTP API the web app uses: the demo site, and design jobs it can start,
poll and inspect.

    GET  /site                                    parcels, extent, sources, open items
    POST /designs {brief, allow_observations,     queue a design; 202 with the job. With
                   product_id}                    product_id, it places that prefab
    POST /designs/{id}/revisions {instruction}    revise its accepted design; 202
    GET  /designs/{id}                            status, attempts, accepted attempt
    GET  /designs/{id}/attempts/{n}/{file}        design.glb, design.png, observation-k.png,
                                                  visual.png, visual.json
    GET  /designs/{id}/products                   real prefabs that fit it (``api.products``)

The surveyed site features are served too (``api.features``). A public server
caps the design runs it starts a day (``api.limits``), and can fix the survey
as someone decided it. Only those
artifact names are served, and only as regular files in the job's own run
directory: never through a symlink.
"""

import re
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from button_nz.api.aerial import SiteAerial, aerial_router, aerial_view
from button_nz.api.features import features_router
from button_nz.api.jobs import Worker
from button_nz.api.limits import DailyCap
from button_nz.api.products import products_router
from button_nz.api.store import Job, Placed, Store
from button_nz.catalogue import Product, load_products
from button_nz.demo_site import DemoSite

ARTIFACT = re.compile(
    r"design\.glb|design\.png|observation-[1-9][0-9]*\.png|visual\.png|visual\.json"
)


class DesignRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    allow_observations: bool = True
    product_id: str | None = None  # a catalogue product to place, walls and all


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    allow_observations: bool = True


class AttemptView(BaseModel):
    number: int
    status: str  # pass, fail, unknown or error
    feedback: str
    observations: list[str]
    files: dict[str, str]  # artifact name -> URL


class ProductView(BaseModel):
    id: str
    name: str
    length_m: float
    width_m: float


class JobView(BaseModel):
    id: str
    brief: str
    allow_observations: bool
    status: str  # queued, running, done or failed
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    accepted_attempt: int | None
    parent_id: str | None
    instruction: str | None
    product: ProductView | None  # the prefab it places
    attempts: list[AttemptView]
    illustrating: bool  # done, and its AI visual is still being made: look again


def create_app(
    store: Store,
    worker: Worker,
    site: DemoSite,
    survey: Path | None = None,
    aerial: SiteAerial | None = None,
    products: Sequence[Product] | None = None,
    cap: DailyCap | None = None,
    survey_decided_by: str | None = None,
) -> FastAPI:
    """The API. ``cap`` limits the design runs started a day; with
    ``survey_decided_by``, the survey is fixed as that person decided it."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        store.recover()
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="button-nz", lifespan=lifespan)
    site_view = _site(site) | {"aerial": aerial_view(aerial)}
    app.include_router(features_router(store, survey, survey_decided_by))
    app.include_router(aerial_router(aerial))
    catalogue = load_products() if products is None else products
    app.include_router(products_router(store, worker.runs_dir, catalogue))
    placeable = {p.id: p for p in catalogue if p.placeable}

    @app.get("/site")
    def get_site() -> dict[str, Any]:
        return site_view

    @app.post("/designs", status_code=202)
    def post_design(request: DesignRequest) -> JobView:
        placed = _placed(placeable, request.product_id)
        with _admit(cap):
            job = store.create_job(request.brief, request.allow_observations, product=placed)
        worker.wake()
        return _job_view(store, worker, job)

    @app.post("/designs/{job_id}/revisions", status_code=202)
    def post_revision(job_id: str, request: RevisionRequest) -> JobView:
        parent = _job(store, job_id)
        if parent.accepted_attempt is None:
            raise HTTPException(409, f"design {job_id} has no accepted attempt to revise")
        with _admit(cap):
            job = store.create_job(
                parent.brief,
                request.allow_observations,
                parent.id,
                request.instruction,
                parent.product,
            )
        worker.wake()
        return _job_view(store, worker, job)

    @app.get("/designs/{job_id}")
    def get_design(job_id: str) -> JobView:
        return _job_view(store, worker, _job(store, job_id))

    @app.get("/designs/{job_id}/attempts/{number}/{name}")
    def get_artifact(job_id: str, number: int, name: str) -> FileResponse:
        path = _artifact(_attempt_dir(worker, _job(store, job_id), number), name)
        if path is None:
            raise HTTPException(404, f"no {name} for attempt {number}")
        return FileResponse(path)

    return app


def _admit(cap: DailyCap | None) -> AbstractContextManager[None]:
    """Hold the daily cap while a design run is created, if there is one."""
    return nullcontext() if cap is None else cap.admit()


def _placed(placeable: Mapping[str, Product], product_id: str | None) -> Placed | None:
    """The product to place, as the catalogue gives it now; a 422 for one whose
    footprint isn't a known rectangle."""
    if product_id is None:
        return None
    if product_id not in placeable:
        raise HTTPException(422, f"{product_id} isn't a product whose footprint can be placed")
    footprint = placeable[product_id].footprint()
    return Placed(product_id, footprint.name, footprint.length_m, footprint.width_m)


def _job(store: Store, job_id: str) -> Job:
    try:
        return store.get_job(job_id)
    except KeyError:
        raise HTTPException(404, f"no design {job_id}") from None


def _attempt_dir(worker: Worker, job: Job, number: int) -> Path:
    return worker.runs_dir / job.id / f"attempt-{number}"


def _job_view(store: Store, worker: Worker, job: Job) -> JobView:
    attempts = [
        AttemptView(
            number=a.number,
            status=a.status,
            feedback=a.feedback,
            observations=list(a.observations),
            files=_files(worker, job, a.number),
        )
        for a in store.attempts(job.id)
    ]
    return JobView(
        id=job.id,
        brief=job.brief,
        allow_observations=job.allow_observations,
        status=str(job.status),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        accepted_attempt=job.accepted_attempt,
        parent_id=job.parent_id,
        instruction=job.instruction,
        product=None if job.product is None else ProductView(**asdict(job.product)),
        attempts=attempts,
        illustrating=_illustrating(worker, job),
    )


def _illustrating(worker: Worker, job: Job) -> bool:
    """Whether the accepted attempt's visual is still to come: this server makes
    them, the job is done, and ``visual.json`` (written however it went) isn't there."""
    if worker.illustrator is None or job.status != "done" or job.accepted_attempt is None:
        return False
    return not (_attempt_dir(worker, job, job.accepted_attempt) / "visual.json").exists()


def _files(worker: Worker, job: Job, number: int) -> dict[str, str]:
    directory = _attempt_dir(worker, job, number)
    names = sorted(p.name for p in directory.glob("*") if _artifact(directory, p.name))
    return {name: f"/designs/{job.id}/attempts/{number}/{name}" for name in names}


def _artifact(directory: Path, name: str) -> Path | None:
    """``directory/name`` if it is an allowed artifact: a regular file really in
    ``directory``, never a link to somewhere else."""
    path = directory / name
    if not ARTIFACT.fullmatch(name) or path.is_symlink() or not path.is_file():
        return None
    return path if path.resolve().parent == directory.resolve() else None


def _site(site: DemoSite) -> dict[str, Any]:
    features = [
        {
            "type": "Feature",
            "id": parcel.parcel_id,
            "properties": {"appellation": parcel.appellation},
            "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in parcel.ring]]},
        }
        for parcel in site.parcels
    ]
    sources = {name: asdict(source) for name, source in {**site.rasters, **site.vectors}.items()}
    return {
        "name": site.name,
        "title": site.title,
        "valuation_number": site.valuation_number,
        "crs": "EPSG:2193",
        "address": list(site.address_nztm),
        "extent": list(site.extent_nztm),
        "parcels": {"type": "FeatureCollection", "features": features},
        "sources": sources,
        "open_items": list(site.open_items),
    }
