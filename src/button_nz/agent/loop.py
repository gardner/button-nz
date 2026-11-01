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
from enum import StrEnum
from pathlib import Path

from button_nz.agent.conversation import Model, ModelReplyError, Observe, Turn
from button_nz.agent.observe import ObservationError, observe
from button_nz.agent.prompt import describe, placing, system_prompt
from button_nz.agent.proposal import DesignError, parse_measurements, to_proposal
from button_nz.agent.site import DesignSite
from button_nz.blender_worker.run import DesignOutputs, run_design
from button_nz.blender_worker.scene_input import (
    DEFAULT_COLOURS,
    DwellingColours,
    SceneInput,
    with_colours,
)
from button_nz.evaluation import Check, Footprint, InvalidProposal, Report, Status, evaluate

__all__ = [
    "Attempt",
    "DesignResult",
    "DesignSite",
    "Model",
    "Revision",
    "Runner",
    "Turn",
    "design",
]

type Runner = Callable[[SceneInput, str, Path], DesignOutputs]


@dataclass(frozen=True)
class Revision:
    """A design to change: the script that built it, the evaluator's verdict on
    it, and every change the owner has asked for, in their own words, oldest
    first. The script already includes all but the latest change, so only that
    one is asked for; the earlier ones are named so they are kept."""

    script: str
    feedback: str
    instructions: tuple[str, ...]

    @property
    def request(self) -> str:
        *earlier, latest = self.instructions
        if not earlier:
            return latest
        kept = "\n".join(f"- {text}" for text in earlier)
        already = f"This design already includes these earlier changes; keep them:\n{kept}"
        return f"{already}\n\nNow: {latest}"


@dataclass(frozen=True)
class Attempt:
    number: int
    script: str
    feedback: str
    report: Report | None  # None if the script didn't produce a measurable dwelling
    directory: Path
    observations: tuple[str, ...] = ()  # the observation tools used before this attempt
    render: Path | None = None  # this attempt's render, if the runner made one
    judged: bool = False  # the evaluator reached a verdict on it (or rejected it)
    mask: Path | None = None  # the Dwelling's silhouette in the render, if the runner made one

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


class Phase(StrEnum):
    THINKING = "thinking"  # the model is asked for its next move
    OBSERVING = "observing"  # a LiDAR view it asked for is being made
    RENDERING = "rendering"  # Blender runs its script
    CHECKING = "checking"  # the evaluator measures what was rendered


@dataclass(frozen=True)
class Step:
    """What a run has started on: shown to the owner while they wait."""

    attempt: int
    phase: Phase
    detail: str = ""  # the view asked for, when observing


def _no_step(_: Step) -> None:
    pass


def design(
    brief: str,
    site: DesignSite,
    model: Model,
    runs_dir: Path,
    max_attempts: int = 3,
    runner: Runner = run_design,
    allow_observations: bool = True,
    max_observations: int = 4,
    evaluator_feedback: bool = True,
    on_attempt: Callable[[Attempt], None] | None = None,
    revising: Revision | None = None,
    product: Footprint | None = None,
    roof: str | None = None,
    colours: DwellingColours = DEFAULT_COLOURS,
    on_step: Callable[[Step], None] = _no_step,
) -> DesignResult:
    """Design for ``brief`` on ``site``, or, ``revising`` an earlier design,
    change it as the owner asks. Before each attempt the model may request up to
    ``max_observations`` LiDAR views (none if not ``allow_observations``); they
    don't count as attempts. Without ``evaluator_feedback`` the model hears only
    execution errors (Experiment C's ablation): a script that ran ends the run,
    since asking again would tell the model it failed. The evaluator still
    decides acceptance, and every attempt still records its verdict.
    ``on_attempt`` sees each attempt as it ends. Placing a real ``product``, the
    brief gives its footprint (and its ``roof``, in words, where known), and
    every attempt is checked to be it. Every render uses the host's
    ``colours`` for the Dwelling's roof and walls. ``on_step`` hears each step
    as it starts."""
    local = site.frame.to_local
    keep_clear = [tuple(local(p) for p in ring) for ring in site.context.preservation_areas]
    buildings = [tuple(local(p) for p in ring) for ring in site.context.confirmed_buildings]
    prompt = system_prompt(site.scene, keep_clear, buildings)
    asked = brief if product is None else f"{brief}\n\n{placing(product, roof)}"
    scene = with_colours(site.scene, colours)  # the render's colours: the host's, never the model's
    conversation = [Turn("system", prompt), Turn("user", asked)]
    if revising is not None:
        conversation += [
            Turn("design", revising.script),
            Turn("feedback", revising.feedback),
            Turn("user", revising.request),
        ]
    attempts: list[Attempt] = []
    for number in range(1, max_attempts + 1):
        directory = runs_dir / f"attempt-{number}"
        directory.mkdir(parents=True, exist_ok=True)
        ask = _Ask(
            model,
            site,
            conversation,
            directory,
            allow_observations,
            max_observations,
            number,
            on_step,
        )
        script = ask.script()
        if script is None:
            attempt = Attempt(number, "", ask.error, None, directory, ask.observed)
            _write_attempt(attempt)
        else:
            attempt = _attempt(
                number, script, site, scene, runner, directory, ask.observed, product, on_step
            )
        attempts.append(attempt)
        if on_attempt is not None:
            on_attempt(attempt)
        if attempt.report is not None and attempt.report.status is not Status.FAIL:
            break
        if attempt.judged and not evaluator_feedback:  # only errors earn another go
            break
        conversation += [
            Turn("design", attempt.script),
            # The render is evaluator feedback: a contract error can come with one.
            Turn("feedback", attempt.feedback, attempt.render if evaluator_feedback else None),
        ]
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
    number: int  # the attempt's
    on_step: Callable[[Step], None]
    error: str = ""
    observed: tuple[str, ...] = ()

    def script(self) -> str | None:
        for _ in range(self.max_observations + 2):
            self.on_step(Step(self.number, Phase.THINKING))
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
            self.on_step(Step(self.number, Phase.OBSERVING, request.tool))
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
    scene: SceneInput,
    runner: Runner,
    directory: Path,
    observations: tuple[str, ...],
    product: Footprint | None,
    on_step: Callable[[Step], None],
) -> Attempt:
    on_step(Step(number, Phase.RENDERING))
    outputs = runner(scene, script, directory)
    report: Report | None = None
    judged = False
    try:
        measurements = parse_measurements(outputs.measurements)
        datum = site.scene["frame"]["datum_m"]
        proposal = to_proposal(measurements, site.frame, datum)
        judged = True  # from here on, it is the evaluator speaking
        on_step(Step(number, Phase.CHECKING))
        report = evaluate(proposal, site.context, product)
        feedback = describe(report)
    except (DesignError, InvalidProposal) as error:  # feedback for the next attempt
        feedback = str(error)
    attempt = Attempt(
        number, script, feedback, report, directory, observations, outputs.png, judged, outputs.mask
    )
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
