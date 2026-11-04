"""A ready site's relief views (#149), made the first time they're asked for.

    POST /sites/{id}/relief          make them (202), unless they're made or being made
    GET  /sites/{id}/relief          whether they're being made, and ``relief.run``'s
                                     manifest with each file's URL in place of its name
    GET  /sites/{id}/relief/{name}   a file a ready tier names

They're made in the site's own directory (``sites/{id}/relief``) by one
thread, one site after another, so the fly-over never runs beside itself;
its Blender waits for the GPU as every Blender run does (``blender_worker.run``).
A tier the manifest leaves pending or running while nothing is making it was
cut off by a restart: it reads as failed, and asking again makes it again.
"""

import json
import logging
import queue
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from button_nz.perception.survey import PIXEL_M
from button_nz.relief import SiteRelief
from button_nz.relief.run import MANIFEST, ReliefFailed, Tier, publish, run_relief
from button_nz.sites.build import aerial_pixels
from button_nz.sites.registry import DEMO_SITE_ID

if TYPE_CHECKING:
    from button_nz.api.sites import Sites

RELIEF_DIR = "relief"
INTERRUPTED = "interrupted by a restart"
FRESH = {"Cache-Control": "no-store"}  # the manifest changes as each tier starts and ends
CHECKED = {"Cache-Control": "no-cache"}  # a file is rewritten when its tier is made again
log = logging.getLogger(__name__)

type Entries = list[dict[str, Any]]


class ReliefMaker:
    """Makes each site's relief asked for, one site at a time, on its own thread."""

    def __init__(
        self, sites_dir: Path, relief_of: Callable[[str], SiteRelief], tiers: Sequence[Tier]
    ) -> None:
        self.sites_dir, self.relief_of, self.tiers = sites_dir, relief_of, tiers
        self._asked: queue.Queue[str] = queue.Queue()
        self._making: set[str] = set()  # asked for, and not yet made
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def directory(self, site_id: str) -> Path:
        return self.sites_dir / site_id / RELIEF_DIR

    def ask(self, site_id: str) -> None:
        """Make ``site_id``'s relief, unless it's made or being made."""
        with self._lock:
            if site_id in self._making or _made(self._entries(site_id)):
                return
            (self.directory(site_id) / MANIFEST).unlink(missing_ok=True)  # the last try's
            self._making.add(site_id)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name="relief", daemon=True)
                self._thread.start()
        self._asked.put(site_id)

    def shown(self, site_id: str) -> tuple[bool, Entries]:
        """Whether ``site_id``'s relief is being made, and its tiers so far."""
        with self._lock:  # read together: a run ends, and is let go, inside the lock
            making = site_id in self._making
            entries = self._entries(site_id)
        if not making:
            for entry in entries:
                if entry["status"] in ("pending", "running"):
                    entry.update(status="failed", error=INTERRUPTED)
        return making, entries

    def _entries(self, site_id: str) -> Entries:
        path = self.directory(site_id) / MANIFEST
        if not path.is_file():
            return []
        entries: Entries = json.loads(path.read_text("utf-8"))["tiers"]
        return entries

    def _loop(self) -> None:
        while True:
            site_id = self._asked.get()
            try:
                self._make(site_id)
            except Exception:  # never the thread's end: the next site still gets made
                log.exception("the relief of site %s failed", site_id)
            finally:
                with self._lock:
                    self._making.discard(site_id)

    def _make(self, site_id: str) -> None:
        out = self.directory(site_id)
        try:
            relief = self.relief_of(site_id)
        except Exception as error:  # every tier needs it: each says why it wasn't made
            out.mkdir(parents=True, exist_ok=True)
            reason = f"couldn't read the site: {error}"
            publish(
                out, [{"tier": t.name, "status": "failed", "error": reason} for t in self.tiers]
            )
            raise
        try:
            run_relief(relief, out, self.tiers)
        except ReliefFailed as failed:  # the manifest says which and why
            log.warning("site %s's relief: %s", site_id, failed)


def site_relief(sites: Sites, site_id: str) -> SiteRelief:
    """The site's aerial at the survey's ``PIXEL_M`` on its DSM, above its datum,
    as the relief benchmark has it (``bench.relief``)."""
    design, _ = sites.design_site(site_id)
    grid = design.context.terrain
    datum = float(design.scene["frame"]["datum_m"])
    if site_id == DEMO_SITE_ID:
        from button_nz.agent.demo import demo_aerial  # reads LINZ's imagery

        photo = demo_aerial(design, PIXEL_M)
    else:  # a built site's photo is over its LiDAR grid, at PIXEL_M (``sites.build``)
        photo = aerial_pixels((sites.sites_dir / site_id / "aerial.png").read_bytes())
    return SiteRelief(photo, grid.dem + grid.ndsm - datum, grid.cell_m, PIXEL_M)


def relief_router(sites: Sites, maker: ReliefMaker) -> APIRouter:
    router = APIRouter()

    def shown(site_id: str, status_code: int = 200) -> Response:
        making, entries = maker.shown(site_id)
        for entry in entries:
            if "files" in entry:
                entry["files"] = {
                    kind: f"/sites/{site_id}/relief/{name}" for kind, name in entry["files"].items()
                }
        body = {"making": making, "tiers": entries}
        return JSONResponse(body, status_code=status_code, headers=FRESH)

    @router.post("/sites/{site_id}/relief", status_code=202)
    def post_relief(site_id: str) -> Response:
        sites.site(site_id)  # a 404 or 409 for a site there isn't, or isn't ready
        maker.ask(site_id)
        return shown(site_id, 202)

    @router.get("/sites/{site_id}/relief")
    def get_relief(site_id: str) -> Response:
        sites.record(site_id)
        return shown(site_id)

    @router.get("/sites/{site_id}/relief/{name}")
    def get_file(site_id: str, name: str) -> FileResponse:
        sites.record(site_id)
        _, entries = maker.shown(site_id)
        named = {n for e in entries if e["status"] == "ready" for n in e["files"].values()}
        path = maker.directory(site_id) / name
        if name not in named or not path.is_file():
            raise HTTPException(404, f"site {site_id}'s relief has no {name}")
        return FileResponse(path, headers=CHECKED)

    return router


def _made(entries: Entries) -> bool:
    return bool(entries) and all(entry["status"] == "ready" for entry in entries)
