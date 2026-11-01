"""Durable design jobs and their attempts, and a person's decisions about
surveyed site features, in SQLite.

A job moves queued -> running -> done | failed, and only along those edges: a
finished job can't be restarted and a queued one can't be marked done. On
startup, ``recover`` fails any job a crash left running, so nothing looks
in-progress forever. Plain SQL, so the schema ports to Postgres/PostGIS.
"""

import json
import sqlite3
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, get_args

from button_nz.blender_worker.scene_input import DEFAULT_FINISHES, TextureName
from button_nz.catalogue.products import Appearance

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    brief TEXT NOT NULL,
    allow_observations INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    accepted_attempt INTEGER,
    parent_id TEXT REFERENCES jobs (id),
    instruction TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    job_id TEXT NOT NULL REFERENCES jobs (id),
    number INTEGER NOT NULL,
    status TEXT NOT NULL,
    feedback TEXT NOT NULL,
    observations TEXT NOT NULL,
    PRIMARY KEY (job_id, number)
);
CREATE TABLE IF NOT EXISTS decisions (
    survey_id TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    PRIMARY KEY (survey_id, feature_id)
);
CREATE TABLE IF NOT EXISTS surveys (
    survey_id TEXT PRIMARY KEY,
    buildings_complete INTEGER NOT NULL,
    decided_at TEXT NOT NULL
);
"""


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class Placed:
    """A product a design places, as the catalogue gave it when the job was made:
    a later catalogue can't change what the job was designed and checked to."""

    id: str
    name: str
    length_m: float
    width_m: float
    appearance: Appearance | None = None  # how it looks; None for jobs placed before #100


@dataclass(frozen=True)
class Job:
    id: str
    brief: str
    allow_observations: bool
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    accepted_attempt: int | None
    parent_id: str | None = None  # the design this one revises
    instruction: str | None = None  # the owner's change, in their own words
    product: Placed | None = None  # the catalogue product it places, as it was then
    site_id: str | None = None  # the site it is designed on; None: the demo site


@dataclass(frozen=True)
class AttemptRecord:
    job_id: str
    number: int
    status: str  # pass, fail, unknown or error
    feedback: str
    observations: tuple[str, ...]


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            _migrate(db)

    def create_job(
        self,
        brief: str,
        allow_observations: bool,
        parent_id: str | None = None,
        instruction: str | None = None,
        product: Placed | None = None,
        site_id: str | None = None,
    ) -> Job:
        job_id = uuid.uuid4().hex
        with self._db() as db:
            db.execute(
                "INSERT INTO jobs (id, brief, allow_observations, status, created_at, "
                "parent_id, instruction, product, site_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    brief,
                    int(allow_observations),
                    JobStatus.QUEUED,
                    _now(),
                    parent_id,
                    instruction,
                    None if product is None else _placed_json(product),
                    site_id,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Job:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _job(row)

    def created_since(self, since: datetime) -> list[datetime]:
        """When each job created after ``since`` was created, oldest first."""
        with self._db() as db:
            rows = db.execute(
                "SELECT created_at FROM jobs WHERE created_at > ? ORDER BY created_at",
                (since.astimezone(UTC).isoformat(),),
            ).fetchall()
        return [datetime.fromisoformat(row["created_at"]) for row in rows]

    def next_queued(self) -> Job | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at, rowid LIMIT 1",
                (JobStatus.QUEUED,),
            ).fetchone()
        return None if row is None else _job(row)

    def mark_running(self, job_id: str) -> None:
        self._move(job_id, JobStatus.QUEUED, JobStatus.RUNNING, "started_at = ?", (_now(),))

    def mark_done(self, job_id: str, accepted_attempt: int | None) -> None:
        self._move(
            job_id,
            JobStatus.RUNNING,
            JobStatus.DONE,
            "finished_at = ?, accepted_attempt = ?",
            (_now(), accepted_attempt),
        )

    def mark_failed(self, job_id: str, error: str) -> None:
        self._move(
            job_id,
            JobStatus.RUNNING,
            JobStatus.FAILED,
            "finished_at = ?, error = ?",
            (_now(), error),
        )

    def recover(self) -> int:
        """Fail every job left running by a crash or restart; return how many."""
        with self._db() as db:
            cursor = db.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, error = ? WHERE status = ?",
                (JobStatus.FAILED, _now(), "interrupted by a restart", JobStatus.RUNNING),
            )
        return cursor.rowcount

    def accepted_jobs(self) -> list[Job]:
        """Every done job with an accepted attempt."""
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM jobs WHERE status = ? AND accepted_attempt IS NOT NULL",
                (JobStatus.DONE,),
            ).fetchall()
        return [_job(row) for row in rows]

    def add_attempt(self, attempt: AttemptRecord) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO attempts (job_id, number, status, feedback, observations) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    attempt.job_id,
                    attempt.number,
                    attempt.status,
                    attempt.feedback,
                    json.dumps(list(attempt.observations)),
                ),
            )

    def attempts(self, job_id: str) -> tuple[AttemptRecord, ...]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM attempts WHERE job_id = ? ORDER BY number", (job_id,)
            ).fetchall()
        return tuple(
            AttemptRecord(
                row["job_id"],
                row["number"],
                row["status"],
                row["feedback"],
                tuple(json.loads(row["observations"])),
            )
            for row in rows
        )

    def decide(self, survey_id: str, feature_id: str, decision: str) -> None:
        """Record (or change) the decision about a feature of a survey."""
        with self._db() as db:
            db.execute(
                "INSERT INTO decisions (survey_id, feature_id, decision, decided_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (survey_id, feature_id) "
                "DO UPDATE SET decision = excluded.decision, decided_at = excluded.decided_at",
                (survey_id, feature_id, decision, _now()),
            )

    def adopt(self, survey_id: str, suggestions: Mapping[str, str]) -> None:
        """Record each suggestion as a decision, where none has been made yet:
        never over one already made, even one made since the caller looked."""
        now = _now()
        with self._db() as db:
            db.executemany(
                "INSERT INTO decisions (survey_id, feature_id, decision, decided_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (survey_id, feature_id) DO NOTHING",
                [(survey_id, fid, decision, now) for fid, decision in suggestions.items()],
            )

    def decisions(self, survey_id: str) -> dict[str, str]:
        """Every decision made on a survey, by feature id."""
        with self._db() as db:
            rows = db.execute(
                "SELECT feature_id, decision FROM decisions WHERE survey_id = ?", (survey_id,)
            ).fetchall()
        return {row["feature_id"]: row["decision"] for row in rows}

    def set_buildings_complete(self, survey_id: str, complete: bool) -> None:
        """Record whether the person says a survey's buildings are all listed."""
        with self._db() as db:
            db.execute(
                "INSERT INTO surveys (survey_id, buildings_complete, decided_at) "
                "VALUES (?, ?, ?) ON CONFLICT (survey_id) DO UPDATE SET "
                "buildings_complete = excluded.buildings_complete, "
                "decided_at = excluded.decided_at",
                (survey_id, int(complete), _now()),
            )

    def buildings_complete(self, survey_id: str) -> bool:
        with self._db() as db:
            row = db.execute(
                "SELECT buildings_complete FROM surveys WHERE survey_id = ?", (survey_id,)
            ).fetchone()
        return row is not None and bool(row["buildings_complete"])

    def _move(
        self,
        job_id: str,
        source: JobStatus,
        target: JobStatus,
        assignments: str,
        values: tuple[object, ...],
    ) -> None:
        with self._db() as db:
            cursor = db.execute(
                f"UPDATE jobs SET status = ?, {assignments} WHERE id = ? AND status = ?",  # noqa: S608
                (target, *values, job_id, source),
            )
        if cursor.rowcount != 1:
            raise ValueError(f"job {job_id} is {self.get_job(job_id).status}, not {source}")

    @contextmanager
    def _db(self) -> Generator[sqlite3.Connection]:
        """A connection per operation, so the worker thread and request handlers
        never share one; committed on success, rolled back on error."""
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


ADDED_COLUMNS = {  # added after the first release: present in new databases, added to old
    "parent_id": "TEXT REFERENCES jobs (id)",
    "instruction": "TEXT",
    "product": "TEXT",  # the Placed product, as JSON
    "site_id": "TEXT",  # None for jobs made before sites: the demo site
}


def _migrate(db: sqlite3.Connection) -> None:
    """Add any columns a database from an earlier version lacks."""
    present = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    for name, kind in ADDED_COLUMNS.items():
        if name not in present:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _time(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        brief=row["brief"],
        allow_observations=bool(row["allow_observations"]),
        status=JobStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=_time(row["started_at"]),
        finished_at=_time(row["finished_at"]),
        error=row["error"],
        accepted_attempt=row["accepted_attempt"],
        parent_id=row["parent_id"],
        instruction=row["instruction"],
        product=None if row["product"] is None else _placed(json.loads(row["product"])),
        site_id=row["site_id"],
    )


def _placed_json(product: Placed) -> str:
    look = None if product.appearance is None else product.appearance.model_dump(mode="json")
    return json.dumps(asdict(product) | {"appearance": look})


def _placed(raw: dict[str, Any]) -> Placed:
    look = raw.pop("appearance", None)
    return Placed(**raw, appearance=None if look is None else Appearance.parse(_textured(look)))


def _textured(look: dict[str, Any]) -> dict[str, Any]:
    """A snapshotted look keeps its colours; for a texture it lacks (taken before
    products had textures) or the render no longer offers, it takes a bespoke
    design's, so a retired finish can't make the job unreadable."""

    def texture(key: str, default: str) -> str:
        found = look.get(key)
        return found if isinstance(found, str) and found in get_args(TextureName) else default

    return look | {
        "walls_texture": texture("walls_texture", DEFAULT_FINISHES["walls"]["texture"]),
        "roof_texture": texture("roof_texture", DEFAULT_FINISHES["roof"]["texture"]),
    }
