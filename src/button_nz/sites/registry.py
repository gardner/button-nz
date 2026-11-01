"""The sites a server knows: one per LINZ address, kept in SQLite beside the
design jobs, and built by ``SiteBuilder`` one at a time.

A site is ``building`` until its builder ends: ``ready``, ``failed`` (with the
reason) or ``no_lidar`` (no LiDAR covers it). Asking again for a failed site
builds it again; a ``no_lidar`` one stays, since the data won't change. The
demo site is always there, ready, under ``DEMO_SITE_ID``.
"""

import logging
import re
import sqlite3
import threading
import unicodedata
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from button_nz.sites.build import NoLidar, Sources, build_site

DEMO_SITE_ID = "35-victory-street-reefton"
DEMO_ADDRESS_ID = 3213224  # LINZ's 35 Victory Street, Reefton
INTERRUPTED = "interrupted by a restart: ask for the site again"
log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id TEXT PRIMARY KEY,
    address_id INTEGER NOT NULL UNIQUE,
    address TEXT NOT NULL,
    status TEXT NOT NULL,
    step TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS site_builds (
    site_id TEXT NOT NULL REFERENCES sites (id),
    requested_at TEXT NOT NULL
);
"""


class SiteStatus(StrEnum):
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    NO_LIDAR = "no_lidar"


@dataclass(frozen=True)
class SiteRecord:
    id: str
    address_id: int
    address: str
    status: SiteStatus
    step: str | None
    error: str | None
    created_at: datetime


DEMO_RECORD = SiteRecord(
    DEMO_SITE_ID,
    DEMO_ADDRESS_ID,
    "35 Victory Street, Reefton",
    SiteStatus.READY,
    None,
    None,
    datetime(2026, 10, 28, tzinfo=UTC),
)


def slug(address: str) -> str:
    """``12 Cuba Street, Petone`` as ``12-cuba-street-petone``: ASCII, macrons dropped."""
    plain = unicodedata.normalize("NFKD", address).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


class SiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def create(self, address_id: int, address: str) -> SiteRecord:
        """A new site to build for ``address_id``: its id is the address's slug,
        or, if another address has that, the slug and the address id."""
        site_id = slug(address) or str(address_id)
        with self._db() as db:
            if (
                site_id == DEMO_SITE_ID
                or db.execute("SELECT 1 FROM sites WHERE id = ?", (site_id,)).fetchone()
            ):
                site_id = f"{site_id}-{address_id}"
            now = _now()
            db.execute(
                "INSERT INTO sites (id, address_id, address, status, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (site_id, address_id, address, SiteStatus.BUILDING, now),
            )
            db.execute("INSERT INTO site_builds VALUES (?, ?)", (site_id, now))
        return self.get(site_id)

    def get(self, site_id: str) -> SiteRecord:
        if site_id == DEMO_SITE_ID:
            return DEMO_RECORD
        return self._one("SELECT * FROM sites WHERE id = ?", (site_id,), KeyError(site_id))

    def by_address(self, address_id: int) -> SiteRecord | None:
        if address_id == DEMO_ADDRESS_ID:
            return DEMO_RECORD
        try:
            return self._one("SELECT * FROM sites WHERE address_id = ?", (address_id,), KeyError())
        except KeyError:
            return None

    def created_since(self, since: datetime) -> list[datetime]:
        """When each build since ``since`` was asked for, rebuilds included, oldest first."""
        with self._db() as db:
            rows = db.execute(
                "SELECT requested_at FROM site_builds WHERE requested_at > ? ORDER BY requested_at",
                (since.astimezone(UTC).isoformat(),),
            ).fetchall()
        return [datetime.fromisoformat(r["requested_at"]) for r in rows]

    def next_to_build(self) -> SiteRecord | None:
        try:
            return self._one(
                "SELECT * FROM sites WHERE status = ? AND started_at IS NULL "
                "ORDER BY created_at LIMIT 1",
                (SiteStatus.BUILDING,),
                KeyError(),
            )
        except KeyError:
            return None

    def start(self, site_id: str) -> None:
        self._set(site_id, "started_at = ?, step = NULL", (_now(),))

    def step(self, site_id: str, step: str) -> None:
        self._set(site_id, "step = ?", (step,))

    def finish(self, site_id: str, status: SiteStatus, error: str | None = None) -> None:
        self._set(
            site_id, "status = ?, error = ?, step = NULL, finished_at = ?", (status, error, _now())
        )

    def rebuild(self, site_id: str) -> None:
        """Build a failed site again, from the start: another build request."""
        now = _now()
        self._set(
            site_id,
            "status = ?, error = NULL, step = NULL, started_at = NULL, finished_at = NULL, "
            "created_at = ?",
            (SiteStatus.BUILDING, now),
        )
        with self._db() as db:
            db.execute("INSERT INTO site_builds VALUES (?, ?)", (site_id, now))

    def recover(self) -> int:
        """Fail every build a restart cut off; return how many."""
        with self._db() as db:
            cursor = db.execute(
                "UPDATE sites SET status = ?, error = ?, finished_at = ? "
                "WHERE status = ? AND started_at IS NOT NULL",
                (SiteStatus.FAILED, INTERRUPTED, _now(), SiteStatus.BUILDING),
            )
        return cursor.rowcount

    def _set(self, site_id: str, assignments: str, values: tuple[object, ...]) -> None:
        with self._db() as db:
            db.execute(f"UPDATE sites SET {assignments} WHERE id = ?", (*values, site_id))

    def _one(self, sql: str, params: tuple[object, ...], missing: KeyError) -> SiteRecord:
        with self._db() as db:
            row = db.execute(sql, params).fetchone()
        if row is None:
            raise missing
        return SiteRecord(
            id=row["id"],
            address_id=row["address_id"],
            address=row["address"],
            status=SiteStatus(row["status"]),
            step=row["step"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @contextmanager
    def _db(self) -> Generator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


class SiteBuilder:
    """Builds queued sites one at a time, in a thread of its own, so a site can
    be built while a design runs."""

    def __init__(self, store: SiteStore, sites_dir: Path, sources: Callable[[], Sources]) -> None:
        self.store, self.sites_dir, self.sources = store, sites_dir, sources
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None

    def run_next(self) -> bool:
        site = self.store.next_to_build()
        if site is None:
            return False
        self.store.start(site.id)
        try:
            build_site(
                site.address_id,
                self.sites_dir / site.id,
                self.sources(),
                lambda step: self.store.step(site.id, step),
            )
        except NoLidar as error:
            self.store.finish(site.id, SiteStatus.NO_LIDAR, str(error))
        except Exception as error:  # the site's failure, recorded rather than lost
            log.exception("building site %s failed", site.id)
            self.store.finish(site.id, SiteStatus.FAILED, f"{type(error).__name__}: {error}")
        else:
            self.store.finish(site.id, SiteStatus.READY)
        return True

    def start(self) -> None:
        self.store.recover()
        self._thread = threading.Thread(target=self._loop, name="site-builder", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout_s)

    def _loop(self) -> None:
        while not self._stop.is_set():
            while not self._stop.is_set() and self.run_next():
                pass
            self._wake.wait()
            self._wake.clear()


def _now() -> str:
    return datetime.now(UTC).isoformat()
