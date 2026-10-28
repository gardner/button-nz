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

from button_nz.agent.conversation import Model, ModelReplyError, Observe, Turn
from button_nz.agent.observe import ObservationError, observe
from button_nz.agent.prompt import describe, system_prompt
from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.agent.site import DesignSite
from button_nz.blender_worker.run import DesignOutputs, run_design
from button_nz.blender_worker.scene_input import SceneInput
from button_nz.evaluation import Check, InvalidProposal, Report, Status, evaluate

__all__ = ["Attempt", "DesignResult", "DesignSite", "Model", "Runner", "Turn", "design"]

type Runner = Callable[[SceneInput, str, Path], DesignOutputs]


@dataclass(frozen=True)
class Attempt:
    number: int
    script: str
    feedback: str
    report: Report | None  # None if the script didn't produce a measurable dwelling
    directory: Path
    observations: tuple[str, ...] = ()  # the observation tools used before this attempt
    render: Path | None = None  # this attempt's render, if the runner made one

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
    allow_observations: bool = True,
    max_observations: int = 4,
    on_attempt: Callable[[Attempt], None] | None = None,
) -> DesignResult:
    """Design for ``brief`` on ``site``. Before each attempt the model may request
    up to ``max_observations`` LiDAR views (none if not ``allow_observations``);
    they don't count as attempts. ``on_attempt`` sees each attempt as it ends."""
    conversation = [Turn("system", system_prompt(site.scene)), Turn("user", brief)]
    attempts: list[Attempt] = []
    for number in range(1, max_attempts + 1):
        directory = runs_dir / f"attempt-{number}"
        directory.mkdir(parents=True, exist_ok=True)
        ask = _Ask(model, site, conversation, directory, allow_observations, max_observations)
        script = ask.script()
        if script is None:
            attempt = Attempt(number, "", ask.error, None, directory, ask.observed)
            _write_attempt(attempt)
        else:
            attempt = _attempt(number, script, site, runner, directory, ask.observed)
        attempts.append(attempt)
        if on_attempt is not None:
            on_attempt(attempt)
        conversation += [
            Turn("design", attempt.script),
            Turn("feedback", attempt.feedback, attempt.render),
        ]
        if attempt.report is not None and attempt.report.status is not Status.FAIL:
            break
    result = DesignResult(brief, tuple(attempts))
    _write_summary(result, runs_dir)
    return result


@dataclass
class _Ask:
    """One attempt's exchange: answer observation requests until a script arrives.
    Once the budget is spent the model is offered only the script tool, and has
    two more turns to use it before the attempt is lost."""

    model: Model
    site: DesignSite
    conversation: list[Turn]
    directory: Path
    allow_observations: bool
    max_observations: int
    error: str = ""
    observed: tuple[str, ...] = ()

    def script(self) -> str | None:
        for _ in range(self.max_observations + 2):
            try:
                action = self.model.propose(self.conversation, self._may_observe())
            except ModelReplyError as error:
                self.error = str(error)
                return None
            if isinstance(action, str):
                return action
            self._answer(action)
        self.error = (
            f"You used all {self.max_observations} observations without submitting a design. "
            "Call run_blender_script with your design."
        )
        return None

    def _answer(self, request: Observe) -> None:
        self.conversation.append(
            Turn(
                "request", json.dumps({"tool": request.tool, "arguments": dict(request.arguments)})
            )
        )
        if not self.allow_observations:
            text, image = "Observations are not available in this run; submit a design.", None
        elif not self._may_observe():
            text, image = "No observations left for this attempt; submit a design.", None
        else:
            self.observed += (request.tool,)
            text, image = self._observe(request)
            text += f"\n\n{self._left()} left for this attempt."
        self.conversation.append(Turn("observation", text, image))

    def _may_observe(self) -> bool:
        return self.allow_observations and len(self.observed) < self.max_observations

    def _left(self) -> str:
        left = self.max_observations - len(self.observed)
        return f"{left} observation{'' if left == 1 else 's'}"

    def _observe(self, request: Observe) -> tuple[str, Path | None]:
        try:
            observation = observe(self.site, request)
        except ObservationError as error:
            return str(error), None
        if observation.png is None:
            return observation.text, None
        image = self.directory / f"observation-{len(self.observed)}.png"
        image.write_bytes(observation.png)
        return observation.text, image


def _attempt(
    number: int,
    script: str,
    site: DesignSite,
    runner: Runner,
    directory: Path,
    observations: tuple[str, ...],
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
    attempt = Attempt(number, script, feedback, report, directory, observations, outputs.png)
    _write_attempt(attempt)
    return attempt


def _write_attempt(attempt: Attempt) -> None:
    checks: tuple[Check, ...] = () if attempt.report is None else attempt.report.checks
    trace = {
        "number": attempt.number,
        "status": attempt.status,
        "script": attempt.script,
        "feedback": attempt.feedback,
        "observations": list(attempt.observations),
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
