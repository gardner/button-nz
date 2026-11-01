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

import json
import re
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AbstractContextManager, asynccontextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from button_nz.api.aerial import SiteAerial, aerial_router, aerial_view
from button_nz.api.features import features_router, site_features_router
from button_nz.api.fixed import FixedSurvey, SurveyReplaced
from button_nz.api.jobs import Worker
from button_nz.api.limits import DailyCap
from button_nz.api.products import products_router
from button_nz.api.site_view import site_view as view_of
from button_nz.api.sites import Sites, SiteService, sites_router
from button_nz.api.store import Job, Placed, Store
from button_nz.catalogue import Product, load_products
from button_nz.demo_site import DemoSite
from button_nz.sites.design_map import design_layers, scene_frame
from button_nz.sites.registry import DEMO_SITE_ID

ARTIFACT = re.compile(
    r"design\.glb|design\.png|observation-[1-9][0-9]*\.png|visual\.png|visual\.json"
)


class DesignRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    allow_observations: bool = True
    product_id: str | None = None  # a catalogue product to place, walls and all
    # The site to design on; omitted (None), the demo site. Never empty: an empty
    # id is a client's mistake, not a request for the demo (422).
    site_id: str | None = Field(default=None, min_length=1, max_length=200)


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    allow_observations: bool = True


class AttemptView(BaseModel):
    number: int
    status: str  # pass, fail, unknown or error
    feedback: str
    observations: list[str]
    files: dict[str, str]  # artifact name -> URL
    # every check: name, status, detail, measured, rule; None: its trace is missing
    checks: list[dict[str, Any]] | None


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
    site_id: str  # the site it is designed on
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
    fixed_survey: FixedSurvey | None = None,
    sites: SiteService | None = None,
) -> FastAPI:
    """The API. ``cap`` limits the design runs started a day; with
    ``fixed_survey``, the survey is fixed as that person decided it: a
    survey file replaced since is refused (409), never served undecided."""

    where = Where(site, survey, None if sites is None else sites.sites)
    threads, routers = _with_sites(sites, store, worker)
    routers.append(_design_map_router(store, worker, where))
    app = FastAPI(title="button-nz", lifespan=_lifespan(store, threads))
    site_view = view_of(site) | {"aerial": aerial_view(aerial)}
    app.include_router(features_router(store, survey, fixed_survey))

    @app.exception_handler(SurveyReplaced)
    def survey_replaced(_: Request, error: SurveyReplaced) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=409)

    app.include_router(aerial_router(aerial))
    for router in routers:
        app.include_router(router)
    catalogue = load_products() if products is None else products
    app.include_router(products_router(store, worker.runs_dir, catalogue, scene_frame))
    placeable = {p.id: p for p in catalogue if p.placeable}

    @app.get("/site")
    def get_site() -> dict[str, Any]:
        return site_view

    @app.post("/designs", status_code=202)
    def post_design(request: DesignRequest) -> JobView:
        placed = _placed(placeable, request.product_id)
        site_id = where.ready(DEMO_SITE_ID if request.site_id is None else request.site_id)
        with _admit(cap):
            job = store.create_job(
                request.brief, request.allow_observations, product=placed, site_id=site_id
            )
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
                parent.site_id,
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


@dataclass(frozen=True)
class Where:
    """Which site a design is on: the demo site, or, with ``sites``, any other."""

    demo: DemoSite
    demo_survey: Path | None
    sites: Sites | None

    def ready(self, site_id: str) -> str:
        """``site_id``, if a design can be made there now; else a 404 or 409."""
        if self.sites is not None:
            self.sites.site(site_id)
        elif site_id != DEMO_SITE_ID:
            raise HTTPException(404, f"this server designs only on the demo site, not {site_id}")
        return site_id

    def survey(self, job: Job) -> Path | None:
        site_id = job.site_id or DEMO_SITE_ID
        return self.demo_survey if self.sites is None else self.sites.survey(site_id)[0]


def _design_map_router(store: Store, worker: Worker, where: Where) -> APIRouter:
    router = APIRouter()

    @router.get("/designs/{job_id}/map")
    def get_design_map(job_id: str) -> dict[str, Any]:
        job = _job(store, job_id)
        if job.accepted_attempt is None:
            raise HTTPException(409, f"design {job_id} has no accepted attempt to map")
        attempt = _attempt_dir(worker, job, job.accepted_attempt)
        return design_layers(attempt, lambda: where.survey(job))

    return router


def _checks(attempt: Path) -> list[dict[str, Any]] | None:
    """The attempt's checks, as its trace recorded them; None if it has no trace."""
    trace = attempt / "attempt.json"
    if not trace.is_file():
        return None
    checks: list[dict[str, Any]] = json.loads(trace.read_text(encoding="utf-8"))["checks"]
    return checks


class _Thread(Protocol):
    def start(self) -> None: ...
    def stop(self, timeout_s: float = 5.0) -> None: ...


def _with_sites(
    sites: SiteService | None, store: Store, worker: Worker
) -> tuple[list[_Thread], list[APIRouter]]:
    """The threads to run and the extra routes, with or without any-address sites."""
    if sites is None:
        return [worker], []
    routers = [sites_router(sites, store), site_features_router(store, sites.sites.survey)]
    return [worker, sites.builder], routers


def _lifespan(store: Store, threads: Sequence[_Thread]) -> Any:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        store.recover()
        for thread in threads:
            thread.start()
        yield
        for thread in threads:
            thread.stop()

    return lifespan


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
    look = placeable[product_id].appearance
    return Placed(product_id, footprint.name, footprint.length_m, footprint.width_m, look)


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
            checks=_checks(_attempt_dir(worker, job, a.number)),
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
        product=None if job.product is None else _product_view(job.product),
        site_id=job.site_id or DEMO_SITE_ID,
        attempts=attempts,
        illustrating=_illustrating(worker, job),
    )


def _product_view(product: Placed) -> ProductView:
    return ProductView(
        id=product.id, name=product.name, length_m=product.length_m, width_m=product.width_m
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
