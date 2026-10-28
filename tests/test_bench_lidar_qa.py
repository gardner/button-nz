"""Tests for button_nz.bench.lidar_qa: asking, scoring and reporting Experiment A."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.agent.conversation import ModelReplyError, Observe
from button_nz.agent.site import DesignSite
from button_nz.bench.answering import QaTurn
from button_nz.bench.lidar_qa import Result, ask, report, run, summarise
from button_nz.bench.questions import Mark, Question
from button_nz.bench.views import SCALE
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

PARCEL: Ring = ((5.0, 5.0), (35.0, 5.0), (35.0, 25.0), (5.0, 25.0), (5.0, 5.0))
ASPECT = Question("aspect-1", "aspect", "Which way?", (Mark("A", 0.0, 0.0),), "W", ("W", "E"))
RELIEF = Question("relief-1", "relief", "How much?", (Mark("A", 0, 0, 5.0),), 1.0, (), 0.2)


@pytest.fixture
def site() -> DesignSite:
    x = np.tile(np.arange(40, dtype=np.float64) + 0.5, (30, 1))
    grid = TerrainGrid((0.0, 0.0, 40.0, 30.0), 1.0, 100.0 + 0.1 * x, np.zeros_like(x), ("t",))
    frame = LocalFrame.centred_on(grid.bbox)
    return DesignSite(
        scene_input(grid, frame, [PARCEL]), frame, SiteContext(parcels=(PARCEL,), terrain=grid)
    )


@pytest.fixture
def aerial() -> NDArray[np.uint8]:
    return np.full((30 * SCALE, 40 * SCALE, 3), 128, dtype=np.uint8)


class Scripted:
    def __init__(self, *replies: str | Observe | Exception) -> None:
        self.replies = list(replies)
        self.seen: list[list[QaTurn]] = []
        self.allowed: list[bool] = []

    def answer(self, turns: Sequence[QaTurn], allow_observations: bool) -> str | Observe:
        self.seen.append(list(turns))
        self.allowed.append(allow_observations)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_a_question_is_asked_with_its_conditions_images_and_scored(
    site: DesignSite, aerial: NDArray[np.uint8]
) -> None:
    model = Scripted("W")
    result = ask(ASPECT, "aerial_ndsm_slope", site, aerial, model)
    assert result.correct and result.answer == "W" and result.error is None
    question = model.seen[0][1]
    assert question.role == "question" and "Which way?" in question.text
    assert len(question.images) == 3
    assert model.allowed == [False]


def test_the_agent_may_look_before_answering(site: DesignSite, aerial: NDArray[np.uint8]) -> None:
    model = Scripted(Observe("render_height_map", {"mode": "slope"}), "0.9")
    result = ask(RELIEF, "agent", site, aerial, model)
    assert result.observations == ("render_height_map",)
    assert result.correct  # 0.9 is within 0.2 of 1.0
    observation = model.seen[1][-1]
    assert observation.role == "observation" and observation.images
    assert model.allowed == [True, True]


def test_the_agent_must_answer_once_its_budget_is_spent(
    site: DesignSite, aerial: NDArray[np.uint8]
) -> None:
    slope = Observe("render_height_map", {"mode": "slope"})
    model = Scripted(slope, slope, "1.0")
    result = ask(RELIEF, "agent", site, aerial, model, max_observations=2)
    assert model.allowed == [True, True, False]
    assert result.correct


def test_a_reply_without_an_answer_is_a_wrong_answer_with_its_error(
    site: DesignSite, aerial: NDArray[np.uint8]
) -> None:
    result = ask(ASPECT, "aerial", site, aerial, Scripted(ModelReplyError("no answer")))
    assert not result.correct and result.answer is None and result.error == "no answer"


def test_runs_are_written_as_they_go(
    site: DesignSite, aerial: NDArray[np.uint8], tmp_path: Path
) -> None:
    model = Scripted("W", "E")
    results = run([ASPECT], ["aerial", "aerial_contours"], site, aerial, model, tmp_path)
    lines = (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["condition"] for line in lines] == ["aerial", "aerial_contours"]
    assert [r.correct for r in results] == [True, False]


def _result(condition: str, kind: str, correct: bool, error: str | None = None) -> Result:
    return Result(f"{kind}-1", kind, condition, None if error else "x", correct, (), error, 1.0)


def test_summary_counts_by_condition_and_kind() -> None:
    results = [
        _result("aerial", "aspect", True),
        _result("aerial", "aspect", False),
        _result("aerial", "relief", False, error="no answer"),
        _result("agent", "aspect", True),
    ]
    summary = summarise(results)
    assert summary["aerial"]["n"] == 3 and summary["aerial"]["correct"] == 1
    assert summary["aerial"]["errors"] == 1
    assert summary["aerial"]["by_kind"]["aspect"] == {"n": 2, "correct": 1}
    assert summary["agent"]["accuracy"] == 1.0


def test_the_report_states_method_sample_sizes_and_failures() -> None:
    results = [_result("aerial", "aspect", True), _result("aerial", "relief", False)]
    text = report(results, {"model": "muse-spark-1.3", "seed": 7, "questions": 2})
    assert "muse-spark-1.3" in text and "seed 7" in text
    assert "| aerial | 2 | 1 | 50% |" in text
    assert "relief-1" in text  # the failure is listed
