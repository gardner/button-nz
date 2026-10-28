"""Experiment C (plan §11): how much does each kind of feedback help a model
design a dwelling that passes the checks?

    uv run --env-file .env python -m button_nz.bench.design_ablation OUT_DIR \\
        [--repeats 2] [--model muse-spark-1.3] [--effort max] [--conditions a,b] \\
        [--site-context data/demo-site/decisions.json]

The same briefs and conditions with another ``--model`` (e.g. ``muse-wonder-1.0``)
or ``--effort`` compare design models (#47).

Each brief is designed under each condition, ``repeats`` times, as a full run
of the design loop (sandboxed Blender, independent evaluator) kept under
``OUT_DIR/runs``. ``results.jsonl`` gets a line per run as it ends, and
``report.md`` is written from those lines alone. A run that can't complete
(e.g. no GPU) is recorded with its error, never dropped.
"""

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from button_nz.agent.conversation import Model
from button_nz.agent.demo import demo_site
from button_nz.agent.loop import Attempt, Runner, design
from button_nz.agent.model import ChatModel
from button_nz.agent.site import DesignSite
from button_nz.blender_worker.run import run_design
from button_nz.perception.confirm import SiteDecisions


@dataclass(frozen=True)
class Condition:
    name: str
    max_attempts: int
    evaluator_feedback: bool
    allow_observations: bool


CONDITIONS = (
    Condition("one_shot", 1, True, False),  # one attempt, nothing back
    Condition("errors", 3, False, False),  # execution errors; a script that runs ends it
    Condition("evaluator", 3, True, False),  # the checks and the render
    Condition("evaluator_lidar", 3, True, True),  # and the LiDAR tools
)
BRIEFS = (
    "A small one-bedroom studio that keeps as much of the garden as possible.",
    "A two-bedroom dwelling of about 60 square metres that gets the afternoon sun.",
    "The largest single-storey granny flat the site allows, set back from the street.",
)


@dataclass(frozen=True)
class RunResult:
    brief: int  # index into the briefs
    condition: str
    repeat: int
    attempts: int
    executed: int  # attempts whose script built a measurable Dwelling (the evaluator judged)
    accepted: bool  # no check failed on the final attempt
    repaired: bool  # accepted after a first attempt that wasn't
    observations: int
    verdicts: tuple[str, ...]  # each attempt's pass, fail, unknown, rejected or error
    seconds: float
    error: str | None  # why the run couldn't complete, if it couldn't


def run(
    briefs: Sequence[str],
    conditions: Sequence[Condition],
    repeats: int,
    site: DesignSite,
    model: Model,
    out_dir: Path,
    runner: Runner = run_design,
) -> list[RunResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / "results.jsonl").exists():  # one run per directory: no mixed results
        raise FileExistsError(f"{out_dir} already holds results; use a new directory")
    results: list[RunResult] = []
    with (out_dir / "results.jsonl").open("x", encoding="utf-8") as log:
        for b, brief in enumerate(briefs):
            for condition in conditions:
                for repeat in range(repeats):
                    runs_dir = out_dir / "runs" / f"brief-{b}" / condition.name / f"run-{repeat}"
                    result = _run_one(b, brief, condition, repeat, site, model, runs_dir, runner)
                    results.append(result)
                    log.write(json.dumps(asdict(result)) + "\n")
                    log.flush()
    return results


def _run_one(
    b: int,
    brief: str,
    condition: Condition,
    repeat: int,
    site: DesignSite,
    model: Model,
    runs_dir: Path,
    runner: Runner,
) -> RunResult:
    started = time.monotonic()
    finished: list[Attempt] = []  # kept if a later attempt can't complete
    try:
        outcome = design(
            brief,
            site,
            model,
            runs_dir,
            condition.max_attempts,
            runner=runner,
            allow_observations=condition.allow_observations,
            evaluator_feedback=condition.evaluator_feedback,
            on_attempt=finished.append,
        )
    except Exception as error:  # recorded, not dropped: the report counts it
        run = _measured(b, condition.name, repeat, finished, None, time.monotonic() - started)
        return replace(run, error=repr(error))
    seconds = time.monotonic() - started
    return _measured(b, condition.name, repeat, outcome.attempts, outcome.accepted, seconds)


def _measured(
    b: int,
    name: str,
    repeat: int,
    attempts: Sequence[Attempt],
    accepted: Attempt | None,
    seconds: float,
) -> RunResult:
    return RunResult(
        brief=b,
        condition=name,
        repeat=repeat,
        attempts=len(attempts),
        executed=sum(a.judged for a in attempts),
        accepted=accepted is not None,
        repaired=accepted is not None and accepted is not attempts[0],
        observations=sum(len(a.observations) for a in attempts),
        verdicts=tuple(_verdict(a) for a in attempts),
        seconds=seconds,
        error=None,
    )


def _verdict(attempt: Attempt) -> str:
    """The attempt's status, telling a proposal the evaluator rejected (it ran and
    was measured) apart from a script that never built a Dwelling."""
    return "rejected" if attempt.judged and attempt.report is None else attempt.status


def summarise(results: Sequence[RunResult]) -> dict[str, dict[str, Any]]:
    """Per condition: runs, accepted, and the rates the plan asks for."""
    summary: dict[str, dict[str, Any]] = {}
    for name in dict.fromkeys(r.condition for r in results):
        mine = [r for r in results if r.condition == name]
        done = [r for r in mine if r.error is None]
        attempts = sum(r.attempts for r in done)
        first_failed = [
            r for r in done if r.verdicts and r.verdicts[0] in ("fail", "rejected", "error")
        ]
        summary[name] = {
            "runs": len(mine),
            "incomplete": len(mine) - len(done),
            "accepted": sum(r.accepted for r in done),
            "execution_rate": sum(r.executed for r in done) / attempts if attempts else None,
            "repair_rate": (
                sum(r.repaired for r in first_failed) / len(first_failed) if first_failed else None
            ),
            "mean_attempts": attempts / len(done) if done else None,
            "mean_observations": sum(r.observations for r in done) / len(done) if done else None,
            "mean_seconds": sum(r.seconds for r in done) / len(done) if done else None,
        }
    return summary


def report(results: Sequence[RunResult], meta: Mapping[str, object]) -> str:
    """Experiment C's report, in Markdown, from ``results`` alone."""
    lines = [
        "# Experiment C: autonomous Blender design",
        "",
        f"Model `{meta['model']}`{_effort(meta)}; {meta['briefs']} briefs x "
        f"{meta['repeats']} repeats per "
        f"condition. Each run is the design loop {_site(meta)}: sandboxed Blender builds "
        "each attempt and the independent evaluator checks it. Accepted means no check "
        "failed on the final attempt; repair rate is over runs whose first attempt failed "
        "or errored. Under `errors` the model hears only execution errors, so a script "
        "that runs ends the run; an incomplete run keeps the attempts that finished.",
        "",
        "| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts "
        "| Mean observations | Mean s | Incomplete |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summarise(results).items():
        accepted = f"{s['accepted']} ({s['accepted'] / s['runs']:.0%})"
        cells = [_rate(s["execution_rate"]), _rate(s["repair_rate"])]
        cells += [_number(s[k]) for k in ("mean_attempts", "mean_observations", "mean_seconds")]
        lines.append(
            f"| {name} | {s['runs']} | {accepted} | {' | '.join(cells)} | {s['incomplete']} |"
        )
    failures = [r for r in results if r.error]
    lines += ["", "## Incomplete runs", ""]
    lines += [f"- brief {r.brief}, {r.condition}, run {r.repeat}: {r.error}" for r in failures] or [
        "None."
    ]
    return "\n".join(lines) + "\n"


def _rate(value: float | None) -> str:
    return "–" if value is None else f"{value:.0%}"


def _site(meta: Mapping[str, object]) -> str:
    site = meta.get("site")
    if site:
        return f"on {site}"
    return "on the demo site, with no confirmed buildings or keep-clear areas"


def _effort(meta: Mapping[str, object]) -> str:
    effort = meta.get("effort")
    return f" (reasoning effort {effort})" if effort else ""


def _number(value: float | None) -> str:
    return "–" if value is None else f"{value:.1f}"


@dataclass(frozen=True)
class Options:
    out_dir: Path
    repeats: int
    model: str
    effort: str | None
    conditions: tuple[Condition, ...]
    site_context: Path | None  # decisions about the surveyed site, if designing on it


def parse_options(argv: Sequence[str] | None = None) -> Options:
    """The command line: where to write, how often, which model and conditions."""
    parser = argparse.ArgumentParser(description="Experiment C: autonomous Blender design.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--model", default="muse-spark-1.3")
    parser.add_argument("--effort", help='reasoning effort, e.g. "max"; default: the API\'s')
    names = ",".join(c.name for c in CONDITIONS)
    parser.add_argument("--conditions", default=names, help=f"some of {names}")
    parser.add_argument(
        "--site-context", type=Path, help="decisions.json: design on the surveyed site"
    )
    args = parser.parse_args(argv)
    by_name = {c.name: c for c in CONDITIONS}
    chosen = args.conditions.split(",")
    unknown = [name for name in chosen if name not in by_name]
    if unknown:
        parser.error(f"unknown condition(s) {', '.join(unknown)}; choose from {names}")
    if len(set(chosen)) != len(chosen):  # each would overwrite the other's runs
        parser.error(f"condition(s) repeated in {args.conditions}")
    conditions = tuple(by_name[name] for name in chosen)
    return Options(
        args.out_dir, args.repeats, args.model, args.effort, conditions, args.site_context
    )


def main(argv: Sequence[str] | None = None) -> None:
    options = parse_options(argv)
    try:
        model = ChatModel.from_env(options.model, options.effort)
    except KeyError as error:
        sys.exit(str(error.args[0]))
    site, described = demo_site(), None
    if options.site_context is not None:
        kept = SiteDecisions.read(options.site_context)
        site = kept.apply(site)
        described = f"the surveyed site (its features decided by {kept.decided_by})"
    results = run(BRIEFS, options.conditions, options.repeats, site, model, options.out_dir)
    meta = {
        "model": model.model,
        "effort": options.effort,
        "site": described,
        "briefs": len(BRIEFS),
        "repeats": options.repeats,
    }
    (options.out_dir / "report.md").write_text(report(results, meta), encoding="utf-8")
    print(json.dumps(summarise(results), indent=2))
    incomplete = [r for r in results if r.error]
    if incomplete:
        sys.exit(f"{len(incomplete)} run(s) could not complete; see report.md")


if __name__ == "__main__":
    main()
