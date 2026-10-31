"""The design worker: runs queued design jobs one at a time (there is one GPU),
recording each attempt as it ends.

A job that raises is marked failed with the reason, e.g. a missing
``META_API_KEY`` or a Blender that couldn't start, so nothing is left looking
in progress. Each job's files are kept under ``runs_dir/<job id>``.

Given an ``illustrator``, a job with an accepted attempt then gets an AI visual
of it (``perception.visual``) once it is marked done: ``visual.json`` says how
that went (until it exists, the visual is still being made), and ``visual.png``
is there only if the visual was accepted. The visual is extra: its failure is
recorded in ``visual.json`` and changes nothing about the job, its verdict or
its acceptance.
"""

import json
import logging
import threading
from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path

from button_nz.agent.conversation import Model
from button_nz.agent.loop import Attempt, DesignSite, Revision, Runner, design
from button_nz.api.store import AttemptRecord, Job, Store
from button_nz.blender_worker.run import run_design
from button_nz.catalogue import Product
from button_nz.evaluation import Footprint
from button_nz.perception.confirm import Decision, Survey, confirmed
from button_nz.perception.visual import VISUAL_JSON, Visual, save

INTERRUPTED = "interrupted by a restart"
log = logging.getLogger(__name__)
NO_SILHOUETTE = "The accepted attempt has no render and dwelling silhouette to illustrate."

type Illustrator = Callable[[Path, Path], Visual]  # (design.png, dwelling-mask.png)


class Worker:
    def __init__(
        self,
        store: Store,
        site: Callable[[], DesignSite],
        model: Callable[[], Model],
        runs_dir: Path,
        runner: Runner = run_design,
        max_attempts: int = 3,
        survey: Path | None = None,
        illustrator: Illustrator | None = None,
        products: Sequence[Product] = (),
    ) -> None:
        self.store = store
        self.products = {p.id: p for p in products}  # what a job may place
        self.site = cache(site)  # read the terrain once, on the first job
        self.survey = survey  # its confirmed features are read afresh for each job
        self.model = model
        self.runs_dir = runs_dir
        self.runner = runner
        self.max_attempts = max_attempts
        self.illustrator = illustrator
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_next(self) -> bool:
        """Run the oldest queued job, if any; return whether there was one."""
        job = self.store.next_queued()
        if job is None:
            return False
        self.store.mark_running(job.id)
        try:
            accepted = self._design(job)
        except Exception as error:  # the job's failure, recorded rather than lost
            log.exception("design job %s failed", job.id)
            self.store.mark_failed(job.id, _reason(error))
        else:
            self.store.mark_done(job.id, None if accepted is None else accepted.number)
            if accepted is not None:  # after: a restart mid-visual mustn't cost the design
                self._illustrate(accepted)
        return True

    def start(self) -> None:
        self.recover_visuals()
        self._thread = threading.Thread(target=self._loop, name="design-worker", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        """A job was queued."""
        self._wake.set()

    def stop(self, timeout_s: float = 5.0) -> None:
        """Stop after the current job. One still running after ``timeout_s`` is
        left to the daemon thread; ``Store.recover`` fails it on the next start."""
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

    def _revising(self, job: Job) -> Revision | None:
        """The parent's accepted design, and every instruction up the chain."""
        if job.parent_id is None or job.instruction is None:
            return None
        parent = self.store.get_job(job.parent_id)
        if parent.accepted_attempt is None:
            raise ValueError(f"design {parent.id} has no accepted attempt to revise")
        instructions = [job.instruction]
        ancestor: Job | None = parent
        while ancestor is not None and ancestor.instruction is not None:
            instructions.insert(0, ancestor.instruction)
            ancestor = self.store.get_job(ancestor.parent_id) if ancestor.parent_id else None
        trace = self.runs_dir / parent.id / f"attempt-{parent.accepted_attempt}" / "attempt.json"
        return _revision(trace, tuple(instructions))

    def recover_visuals(self) -> None:
        """Record every visual a restart cut off, so no job says its visual is
        still coming for ever (``visual.json`` ends the wait, however it went)."""
        if self.illustrator is None:
            return
        for job in self.store.accepted_jobs():
            directory = self.runs_dir / job.id / f"attempt-{job.accepted_attempt}"
            if directory.is_dir() and not (directory / VISUAL_JSON).exists():
                save(Visual.failed(INTERRUPTED), directory)

    def _illustrate(self, accepted: Attempt) -> None:
        """Make and save the visual of ``accepted``; a failure is its record."""
        if self.illustrator is None:
            return
        try:
            if accepted.render is None or accepted.mask is None:
                visual = Visual.failed(NO_SILHOUETTE)
            else:
                visual = self.illustrator(accepted.render, accepted.mask)
        except Exception as error:  # the visual's failure, never the design's
            log.exception("the visual of %s failed", accepted.directory)
            visual = Visual.failed(_reason(error))
        try:
            save(visual, accepted.directory)
        except OSError:
            log.exception("could not save the visual of %s", accepted.directory)

    def _design(self, job: Job) -> Attempt | None:
        def record(attempt: Attempt) -> None:
            self.store.add_attempt(
                AttemptRecord(
                    job.id, attempt.number, attempt.status, attempt.feedback, attempt.observations
                )
            )

        result = design(
            job.brief,
            self._confirmed_site(),
            self.model(),
            self.runs_dir / job.id,
            self.max_attempts,
            runner=self.runner,
            allow_observations=job.allow_observations,
            on_attempt=record,
            revising=self._revising(job),
            product=self._placing(job),
        )
        return result.accepted

    def _placing(self, job: Job) -> Footprint | None:
        """The footprint of the product ``job`` places, if it places one."""
        if job.product_id is None:
            return None
        if job.product_id not in self.products:
            raise ValueError(f"no product {job.product_id} in the catalogue")
        return self.products[job.product_id].footprint()

    def _confirmed_site(self) -> DesignSite:
        """The site with what a person has confirmed on the survey, if any."""
        survey = None if self.survey is None else Survey.read(self.survey)
        if survey is None:
            return self.site()
        decisions = {k: Decision(v) for k, v in self.store.decisions(survey.id).items()}
        complete = self.store.buildings_complete(survey.id)
        return confirmed(self.site(), survey, decisions, complete)


def _revision(trace: Path, instructions: tuple[str, ...]) -> Revision:
    """The accepted attempt a revision starts from, from its trace."""
    attempt = json.loads(trace.read_text(encoding="utf-8"))
    return Revision(attempt["script"], attempt["feedback"], instructions)


def _reason(error: Exception) -> str:
    # KeyError's str() is the repr of its key: show the message itself.
    message = error.args[0] if isinstance(error, KeyError) and error.args else error
    return f"{type(error).__name__}: {message}"
