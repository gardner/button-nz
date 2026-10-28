"""The HTTP API the web app uses: the demo site, and design jobs it can start,
poll and inspect.

    GET  /site                                    parcels, extent, sources, open items
    POST /designs {brief, allow_observations}     queue a design; 202 with the job
    GET  /designs/{id}                            status, attempts, accepted attempt
    GET  /designs/{id}/attempts/{n}/{file}        design.glb, design.png, observation-k.png

Only those artifact names are served, and only as regular files in the job's
own run directory: never through a symlink.
"""

import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from button_nz.api.jobs import Worker
from button_nz.api.store import Job, Store
from button_nz.demo_site import DemoSite

ARTIFACT = re.compile(r"design\.glb|design\.png|observation-[1-9][0-9]*\.png")


class DesignRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    allow_observations: bool = True


class AttemptView(BaseModel):
    number: int
    status: str  # pass, fail, unknown or error
    feedback: str
    observations: list[str]
    files: dict[str, str]  # artifact name -> URL


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
    attempts: list[AttemptView]


def create_app(store: Store, worker: Worker, site: DemoSite) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        store.recover()
        worker.start()
        yield
        worker.stop()

    app = FastAPI(title="button-nz", lifespan=lifespan)
    site_view = _site(site)

    @app.get("/site")
    def get_site() -> dict[str, Any]:
        return site_view

    @app.post("/designs", status_code=202)
    def post_design(request: DesignRequest) -> JobView:
        job = store.create_job(request.brief, request.allow_observations)
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
        attempts=attempts,
    )


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
