"""The design loop: the model writes a Blender script, the sandbox builds it,
the independent evaluator checks what was built, and the model revises.

The loop stops at the first attempt with no failed check, or after
``max_attempts``. Unknown checks are reported, never upgraded to passes, and
whatever the model says, only the evaluator's report decides acceptance.
Every attempt is kept under ``runs_dir`` for inspection.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from button_nz.agent.conversation import Model, ModelReplyError, Turn
from button_nz.agent.prompt import describe, system_prompt
from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.blender_worker.run import DesignOutputs, run_design
from button_nz.blender_worker.scene_input import SceneInput
from button_nz.evaluation import Check, InvalidProposal, Report, SiteContext, Status, evaluate
from button_nz.geo.crs import LocalFrame

__all__ = ["Attempt", "DesignResult", "DesignSite", "Model", "Turn", "design"]

type Runner = Callable[[SceneInput, str, Path], DesignOutputs]


@dataclass(frozen=True)
class DesignSite:
    scene: SceneInput
    frame: LocalFrame
    context: SiteContext


@dataclass(frozen=True)
class Attempt:
    number: int
    script: str
    feedback: str
    report: Report | None  # None if the script didn't produce a measurable dwelling
    directory: Path

    @property
    def status(self) -> str:
        return "error" if self.report is None else str(self.report.status)


@dataclass(frozen=True)
class DesignResult:
    brief: str
    attempts: tuple[Attempt, ...]

    @property
    def accepted(self) -> Attempt | None:
        """The last attempt, if no check failed on it."""
        last = self.attempts[-1] if self.attempts else None
        if last is None or last.report is None or last.report.status is Status.FAIL:
            return None
        return last


def design(
    brief: str,
    site: DesignSite,
    model: Model,
    runs_dir: Path,
    max_attempts: int = 3,
    runner: Runner = run_design,
) -> DesignResult:
    conversation = [Turn("system", system_prompt(site.scene)), Turn("user", brief)]
    attempts: list[Attempt] = []
    for number in range(1, max_attempts + 1):
        directory = runs_dir / f"attempt-{number}"
        try:
            script = model.propose(conversation)
        except ModelReplyError as error:
            script = ""
            attempt = Attempt(number, script, str(error), None, directory)
            directory.mkdir(parents=True, exist_ok=True)
            _write_attempt(attempt)
        else:
            attempt = _attempt(number, script, site, runner, directory)
        attempts.append(attempt)
        image = attempt.directory / "design.png"
        conversation += [
            Turn("design", script),
            Turn("feedback", attempt.feedback, image if image.is_file() else None),
        ]
        if attempt.report is not None and attempt.report.status is not Status.FAIL:
            break
    result = DesignResult(brief, tuple(attempts))
    _write_summary(result, runs_dir)
    return result


def _attempt(
    number: int, script: str, site: DesignSite, runner: Runner, directory: Path
) -> Attempt:
    outputs = runner(site.scene, script, directory)
    report: Report | None = None
    try:
        measurements = parse_measurements(outputs.measurements)
        datum = site.scene["frame"]["datum_m"]
        report = evaluate(to_proposal(measurements, site.frame, datum), site.context)
        feedback = describe(report)
    except (DesignError, InvalidProposal) as error:  # feedback for the next attempt
        feedback = str(error)
    attempt = Attempt(number, script, feedback, report, directory)
    _write_attempt(attempt)
    return attempt


def _write_attempt(attempt: Attempt) -> None:
    checks: tuple[Check, ...] = () if attempt.report is None else attempt.report.checks
    trace = {
        "number": attempt.number,
        "status": attempt.status,
        "script": attempt.script,
        "feedback": attempt.feedback,
        "checks": [
            {
                "name": c.name,
                "status": str(c.status),
                "detail": c.detail,
                "measured": dict(c.measured),
                "rule": c.rule,
            }
            for c in checks
        ],
    }
    path = attempt.directory / "attempt.json"
    path.write_text(json.dumps(trace, indent=2), encoding="utf-8")


def _write_summary(result: DesignResult, runs_dir: Path) -> None:
    accepted = result.accepted
    summary = {
        "brief": result.brief,
        "accepted_attempt": None if accepted is None else accepted.number,
        "attempts": [{"number": a.number, "status": a.status} for a in result.attempts],
    }
    (runs_dir / "design.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
