"""Experiment A (plan §11): does a model understand a site's terrain better with
LiDAR views than from the aerial photograph alone, and better still when it
chooses its own views?

    MODEL_API_KEY=... uv run python -m button_nz.bench.lidar_qa OUT_DIR \\
        [--per-kind 10] [--seed 2026]

Every generated question (``bench.questions``) is asked under every condition
(``bench.views``) and scored against the answer computed from the DEM. Results
are appended to ``OUT_DIR/results.jsonl`` as they come, and ``report.md`` is
written from them: nothing is reported that wasn't measured.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from button_nz.agent.conversation import ModelReplyError, Observe
from button_nz.agent.demo import demo_site
from button_nz.agent.observe import ObservationError, observe
from button_nz.agent.site import DesignSite
from button_nz.bench.answering import Answerer, ChatAnswerer, QaTurn
from button_nz.bench.questions import Question, generate, score
from button_nz.bench.views import CONDITIONS, SCALE, condition_images
from button_nz.demo_site import load_demo_site
from button_nz.geo.imagery import read_aerial
from button_nz.geo.tiles import tiles_covering

MAX_OBSERVATIONS = 3
SYSTEM = (
    "You answer questions about the ground on a real New Zealand property. "
    "Coordinates are local metres: x east, y north. Points and squares the "
    "question names are marked in magenta on the images. If tools that show "
    "the site's LiDAR are offered, you may use them first. Answer by calling "
    "submit_answer with only what the question asks for: a direction, a label "
    "or a number."
)


@dataclass(frozen=True)
class Result:
    question: str
    kind: str
    condition: str
    answer: str | None
    correct: bool
    observations: tuple[str, ...]
    error: str | None
    seconds: float


def ask(
    question: Question,
    condition: str,
    site: DesignSite,
    aerial: NDArray[np.uint8],
    answerer: Answerer,
    max_observations: int = MAX_OBSERVATIONS,
) -> Result:
    """Ask ``question`` under ``condition`` and score the answer."""
    started = time.monotonic()
    images = tuple(condition_images(condition, question, site, aerial))
    turns = [QaTurn("system", SYSTEM), QaTurn("question", question.text, images)]
    observed: list[str] = []
    answer, error = None, "kept asking for observations instead of answering"
    try:
        for _ in range(max_observations + 2):
            allowed = condition == "agent" and len(observed) < max_observations
            reply = answerer.answer(turns, allowed)
            if isinstance(reply, str):
                answer, error = reply, None
                break
            turns += _observe(site, reply, allowed, observed)
    except ModelReplyError as reply_error:
        error = str(reply_error)
    return Result(
        question=question.id,
        kind=question.kind,
        condition=condition,
        answer=answer,
        correct=answer is not None and score(question, answer),
        observations=tuple(observed),
        error=error,
        seconds=time.monotonic() - started,
    )


def _observe(
    site: DesignSite, request: Observe, allowed: bool, observed: list[str]
) -> list[QaTurn]:
    turns = [
        QaTurn("request", json.dumps({"tool": request.tool, "arguments": dict(request.arguments)}))
    ]
    if not allowed:
        return [*turns, QaTurn("observation", "No observations are available now: answer.")]
    observed.append(request.tool)
    try:
        view = observe(site, request)
    except ObservationError as error:
        return [*turns, QaTurn("observation", str(error))]
    images = (("The view", view.png),) if view.png else ()
    return [*turns, QaTurn("observation", view.text, images)]


def run(
    questions: Sequence[Question],
    conditions: Sequence[str],
    site: DesignSite,
    aerial: NDArray[np.uint8],
    answerer: Answerer,
    out_dir: Path,
) -> list[Result]:
    """Every question under every condition, each result appended as it ends."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []
    with (out_dir / "results.jsonl").open("a", encoding="utf-8") as log:
        for question in questions:
            for condition in conditions:
                result = ask(question, condition, site, aerial, answerer)
                results.append(result)
                log.write(json.dumps(asdict(result)) + "\n")
                log.flush()
    return results


def summarise(results: Sequence[Result]) -> dict[str, dict[str, Any]]:
    """Per condition: n, correct, errors, accuracy and the same by question kind."""
    summary: dict[str, dict[str, Any]] = {}
    for condition in dict.fromkeys(r.condition for r in results):
        mine = [r for r in results if r.condition == condition]
        by_kind: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "correct": 0})
        for r in mine:
            by_kind[r.kind]["n"] += 1
            by_kind[r.kind]["correct"] += int(r.correct)
        correct = sum(r.correct for r in mine)
        summary[condition] = {
            "n": len(mine),
            "correct": correct,
            "errors": sum(r.error is not None for r in mine),
            "accuracy": correct / len(mine),
            "mean_seconds": sum(r.seconds for r in mine) / len(mine),
            "by_kind": dict(by_kind),
        }
    return summary


def report(results: Sequence[Result], meta: Mapping[str, object]) -> str:
    """Experiment A's report, in Markdown, from ``results`` alone."""
    summary = summarise(results)
    kinds = sorted({r.kind for r in results})
    lines = [
        "# Experiment A: understanding LiDAR",
        "",
        f"Model `{meta['model']}`; {meta['questions']} questions (seed {meta['seed']}), "
        "each asked under every condition and scored against answers computed from the "
        "LiDAR DEM (`button_nz.bench.questions`). Replies without an answer count as wrong.",
        "",
        "| Condition | n | Correct | Accuracy | No answer | Mean s |",
        "|---|---|---|---|---|---|",
    ]
    for condition, s in summary.items():
        lines.append(
            f"| {condition} | {s['n']} | {s['correct']} | {s['accuracy']:.0%} | "
            f"{s['errors']} | {s['mean_seconds']:.1f} |"
        )
    lines += ["", "## By kind (correct / n)", "", f"| Condition | {' | '.join(kinds)} |"]
    lines.append("|---|" + "---|" * len(kinds))
    for condition, s in summary.items():
        cells = [_cell(s["by_kind"].get(kind)) for kind in kinds]
        lines.append(f"| {condition} | {' | '.join(cells)} |")
    lines += ["", "## Wrong answers", ""]
    lines += [
        f"- `{r.question}` ({r.condition}): answered `{r.answer}`"
        + (f"; {r.error}" if r.error else "")
        for r in results
        if not r.correct
    ] or ["None."]
    return "\n".join(lines) + "\n"


def _cell(counts: Mapping[str, int] | None) -> str:
    return "–" if counts is None else f"{counts['correct']}/{counts['n']}"


def demo_aerial(site: DesignSite) -> NDArray[np.uint8]:
    """The demo site's urban aerial over its LiDAR grid, at the views' scale."""
    source = load_demo_site().rasters["aerial"]
    base, scale = source.asset.rsplit("/", 1)[0], int(source.tile.split("_")[1])
    bbox = site.context.terrain.bbox
    assets = [f"{base}/{name}.tiff" for name in tiles_covering(bbox, scale)]
    return read_aerial(assets, bbox, pixel_m=1 / SCALE)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Experiment A: understanding LiDAR.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--per-kind", type=int, default=10)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)
    try:
        answerer = ChatAnswerer.from_env()
    except KeyError as error:
        sys.exit(str(error.args[0]))
    site = demo_site()
    questions = generate(site, args.per_kind, args.seed)
    results = run(questions, CONDITIONS, site, demo_aerial(site), answerer, args.out_dir)
    meta = {"model": answerer.model, "seed": args.seed, "questions": len(questions)}
    (args.out_dir / "report.md").write_text(report(results, meta), encoding="utf-8")
    print(json.dumps(summarise(results), indent=2))


if __name__ == "__main__":
    main()
