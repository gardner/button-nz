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

from button_nz.sites.build import NoLidar, Sources, build_site, build_title_site

DEMO_SITE_ID = "35-victory-street-reefton"
DEMO_ADDRESS_ID = 3213224  # LINZ's 35 Victory Street, Reefton
INTERRUPTED = "interrupted by a restart: ask for the site again"
log = logging.getLogger(__name__)

# A site is built from an address, or, for a title with none, from the
# title: kept by its smallest parcel id.
SITES_COLUMNS = """
    id TEXT PRIMARY KEY,
    address_id INTEGER UNIQUE,
    parcel_id INTEGER UNIQUE,
    address TEXT NOT NULL,
    status TEXT NOT NULL,
    step TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    CHECK (address_id IS NOT NULL OR parcel_id IS NOT NULL)
"""
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS sites ({SITES_COLUMNS});
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
    address_id: int | None  # the LINZ address it was built from
    address: str  # its name: the address, or the title's appellation
    status: SiteStatus
    step: str | None
    error: str | None
    created_at: datetime
    parcel_id: int | None = None  # a title with no address: its smallest parcel id


DEMO_RECORD = SiteRecord(
    DEMO_SITE_ID,
    DEMO_ADDRESS_ID,
    "35 Victory Street, Reefton",
    SiteStatus.READY,
    None,
    None,
    datetime(2026, 10, 28, tzinfo=UTC),
)


def _migrate(db: sqlite3.Connection) -> None:
    """Bring a store made before title sites up to date: rebuild ``sites``
    with a ``parcel_id`` and an ``address_id`` that may be empty, keeping
    every row (SQLite can't drop a NOT NULL in place)."""
    columns = [r[1] for r in db.execute("PRAGMA table_info(sites)").fetchall()]
    if not columns or "parcel_id" in columns:
        return  # a new store, or one already up to date
    kept = ", ".join(c for c in columns)
    db.execute(f"CREATE TABLE sites_new ({SITES_COLUMNS})")
    db.execute(f"INSERT INTO sites_new ({kept}) SELECT {kept} FROM sites")
    db.execute("DROP TABLE sites")
    db.execute("ALTER TABLE sites_new RENAME TO sites")


def slug(address: str) -> str:
    """``12 Cuba Street, Petone`` as ``12-cuba-street-petone``: ASCII, macrons dropped."""
    plain = unicodedata.normalize("NFKD", address).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


class SiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            _migrate(db)
            db.executescript(SCHEMA)

    def create(self, address_id: int, address: str) -> SiteRecord:
        """A new site to build for ``address_id``: its id is the address's slug,
        or, if another site has that, the slug and the address id."""
        return self._insert(address, address_id, None, address_id)

    def create_title(self, parcel_id: int, name: str) -> SiteRecord:
        """A new site for a title with no address, kept by ``parcel_id`` (its
        smallest parcel id) and named ``name`` (its appellation)."""
        return self._insert(name, None, parcel_id, parcel_id)

    def _insert(
        self, name: str, address_id: int | None, parcel_id: int | None, key: int
    ) -> SiteRecord:
        site_id = slug(name) or str(key)
        with self._db() as db:
            if (
                site_id == DEMO_SITE_ID
                or db.execute("SELECT 1 FROM sites WHERE id = ?", (site_id,)).fetchone()
            ):
                site_id = f"{site_id}-{key}"
            now = _now()
            db.execute(
                "INSERT INTO sites (id, address_id, parcel_id, address, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (site_id, address_id, parcel_id, name, SiteStatus.BUILDING, now),
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

    def by_parcel(self, parcel_id: int) -> SiteRecord | None:
        """The title site kept by ``parcel_id``, if there is one."""
        try:
            return self._one("SELECT * FROM sites WHERE parcel_id = ?", (parcel_id,), KeyError())
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
            parcel_id=row["parcel_id"],
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

    def _build(self, site: SiteRecord) -> None:
        """From its address, or, for a title with none, from its parcel."""
        directory = self.sites_dir / site.id

        def step(name: str) -> None:
            self.store.step(site.id, name)

        if site.address_id is not None:
            build_site(site.address_id, directory, self.sources(), step)
        elif site.parcel_id is not None:
            build_title_site(site.parcel_id, site.address, directory, self.sources(), step)
        else:  # the schema's CHECK forbids it
            raise ValueError(f"site {site.id} has neither an address nor a parcel")

    def run_next(self) -> bool:
        site = self.store.next_to_build()
        if site is None:
            return False
        self.store.start(site.id)
        try:
            self._build(site)
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
            self._wake.clear()  # before draining: a request queued meanwhile wakes the next wait
            while not self._stop.is_set() and self.run_next():
                pass
            self._wake.wait()


def _now() -> str:
    return datetime.now(UTC).isoformat()
