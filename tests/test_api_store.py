"""Tests for button_nz.api.store: durable design jobs and their attempts."""

from pathlib import Path

import pytest

from button_nz.api.store import AttemptRecord, JobStatus, Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "button.db")


def test_a_new_job_is_queued(store: Store) -> None:
    job = store.create_job("A small studio.", allow_observations=True)
    assert job.status is JobStatus.QUEUED
    assert store.get_job(job.id) == job
    assert job.created_at.tzinfo is not None


def test_jobs_run_in_order_and_finish(store: Store) -> None:
    first = store.create_job("one", allow_observations=True)
    second = store.create_job("two", allow_observations=False)
    assert store.next_queued() == first
    store.mark_running(first.id)
    assert store.next_queued() == second
    store.mark_done(first.id, accepted_attempt=2)
    done = store.get_job(first.id)
    assert done.status is JobStatus.DONE
    assert done.accepted_attempt == 2
    assert done.started_at is not None and done.finished_at is not None


def test_a_failed_job_keeps_its_error(store: Store) -> None:
    job = store.create_job("one", allow_observations=True)
    store.mark_running(job.id)
    store.mark_failed(job.id, "MODEL_API_KEY is not set")
    failed = store.get_job(job.id)
    assert failed.status is JobStatus.FAILED
    assert failed.error == "MODEL_API_KEY is not set"


@pytest.mark.parametrize("transition", ["done", "failed"])
def test_only_running_jobs_can_finish(store: Store, transition: str) -> None:
    job = store.create_job("one", allow_observations=True)
    with pytest.raises(ValueError, match="queued"):
        if transition == "done":
            store.mark_done(job.id, accepted_attempt=None)
        else:
            store.mark_failed(job.id, "x")


def test_a_job_cannot_start_twice(store: Store) -> None:
    job = store.create_job("one", allow_observations=True)
    store.mark_running(job.id)
    with pytest.raises(ValueError, match="running"):
        store.mark_running(job.id)


def test_attempts_are_recorded_per_job(store: Store) -> None:
    job = store.create_job("one", allow_observations=True)
    store.add_attempt(
        AttemptRecord(job.id, 1, "fail", "title_boundary_setback: fail", ("render_contours",))
    )
    store.add_attempt(AttemptRecord(job.id, 2, "unknown", "ok", ()))
    assert [a.number for a in store.attempts(job.id)] == [1, 2]
    assert store.attempts(job.id)[0].observations == ("render_contours",)


def test_jobs_interrupted_by_a_restart_are_failed_not_resumed(tmp_path: Path) -> None:
    store = Store(tmp_path / "button.db")
    job = store.create_job("one", allow_observations=True)
    store.mark_running(job.id)
    restarted = Store(tmp_path / "button.db")
    assert restarted.recover() == 1
    recovered = restarted.get_job(job.id)
    assert recovered.status is JobStatus.FAILED
    assert recovered.error == "interrupted by a restart"


def test_an_unknown_job_raises(store: Store) -> None:
    with pytest.raises(KeyError):
        store.get_job("nope")


def test_a_revision_records_what_it_revises(store: Store) -> None:
    parent = store.create_job("A studio.", allow_observations=True)
    child = store.create_job(
        "A studio.", allow_observations=False, parent_id=parent.id, instruction="Face north."
    )
    assert store.get_job(child.id).parent_id == parent.id
    assert store.get_job(child.id).instruction == "Face north."
    assert store.get_job(parent.id).parent_id is None
