"""Durable design jobs and their attempts, in SQLite.

A job moves queued -> running -> done | failed, and only along those edges: a
finished job can't be restarted and a queued one can't be marked done. On
startup, ``recover`` fails any job a crash left running, so nothing looks
in-progress forever. Plain SQL, so the schema ports to Postgres/PostGIS.
"""

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

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
"""


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


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
    ) -> Job:
        job_id = uuid.uuid4().hex
        with self._db() as db:
            db.execute(
                "INSERT INTO jobs (id, brief, allow_observations, status, created_at, "
                "parent_id, instruction) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    brief,
                    int(allow_observations),
                    JobStatus.QUEUED,
                    _now(),
                    parent_id,
                    instruction,
                ),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Job:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _job(row)

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
    )
