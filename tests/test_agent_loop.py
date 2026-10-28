"""Tests for button_nz.agent.loop with a scripted model and a fake Blender runner."""

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.conversation import ModelReplyError, Observe
from button_nz.agent.loop import DesignResult, DesignSite, Revision, Turn, design
from button_nz.blender_worker.run import DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.evaluation import SiteContext, Status
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid
from meshes import box

# One 40 m x 20 m parcel; the local frame's origin is NZTM (0, 0), datum 100 m.
PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
GOOD = {
    "triangles": box(15, 7, 0.3, 21, 12, 3.9),
    "floor_area_m2": 26.0,
    "storeys": 1,
}
NEAR = GOOD | {"triangles": box(0.5, 7, 0.3, 6.5, 12, 3.9)}  # 0.5 m from the title boundary
BROKEN = {"error": 'Traceback (most recent call last):\n  File "design.py", line 1\nNameError: x'}
OFF_TERRAIN = GOOD | {"triangles": box(38, 7, 0.3, 44, 12, 3.9)}  # past the terrain's east edge
MEASURED = {"good": GOOD, "near": NEAR, "broken": BROKEN, "off": OFF_TERRAIN}


@pytest.fixture
def site() -> DesignSite:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    scene = scene_input(grid, frame, [PARCEL])
    return DesignSite(scene, frame, SiteContext(parcels=(PARCEL,), terrain=grid))


class ScriptedModel:
    """Replays scripts in order and records every conversation it was shown."""

    def __init__(self, *scripts: str | Observe) -> None:
        self.scripts = list(scripts)
        self.seen: list[list[Turn]] = []
        self.allowed: list[bool] = []

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        self.seen.append(list(conversation))
        self.allowed.append(allow_observations)
        return self.scripts.pop(0)


def fake_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    out_dir.mkdir(parents=True, exist_ok=True)
    measurements = {"error": None} | MEASURED[script.strip()]
    png = out_dir / "design.png"
    png.write_bytes(b"png")
    failed = measurements.get("error") is not None
    return DesignOutputs(measurements, out_dir / "design.py", None, None if failed else png)


def run(
    site: DesignSite,
    model: ScriptedModel,
    tmp_path: Path,
    attempts: int = 3,
    allow_observations: bool = True,
) -> DesignResult:
    return design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        attempts,
        runner=fake_runner,
        allow_observations=allow_observations,
        max_observations=2,
    )


def test_a_failed_check_is_fed_back_and_the_revision_accepted(
    site: DesignSite, tmp_path: Path
) -> None:
    model = ScriptedModel("near", "good")
    result = run(site, model, tmp_path)
    assert [a.report.status if a.report else None for a in result.attempts] == [
        Status.FAIL,
        Status.UNKNOWN,  # no fail; building separation stays unknown
    ]
    assert result.accepted is result.attempts[1]
    feedback = model.seen[1][-1]
    assert feedback.role == "feedback"
    assert "title_boundary_setback: fail" in feedback.text
    assert "0.50 m from the title boundary" in feedback.text
    assert feedback.image == tmp_path / "attempt-1" / "design.png"


def test_a_script_error_is_fed_back(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("broken", "good")
    result = run(site, model, tmp_path)
    assert result.attempts[0].report is None
    assert "NameError" in model.seen[1][-1].text
    assert result.accepted is result.attempts[1]


def test_it_gives_up_after_the_attempt_limit(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("near", "near", "near", "good")
    result = run(site, model, tmp_path, attempts=3)
    assert len(result.attempts) == 3
    assert result.accepted is None


def test_the_conversation_starts_with_the_contract_and_the_brief(
    site: DesignSite, tmp_path: Path
) -> None:
    model = ScriptedModel("good")
    run(site, model, tmp_path)
    system, brief = model.seen[0]
    assert system.role == "system"
    assert "Dwelling" in system.text
    assert "2 m" in system.text
    assert brief.role == "user"
    assert "Add a small dwelling." in brief.text


def test_every_attempt_is_traced_on_disk(site: DesignSite, tmp_path: Path) -> None:
    run(site, ScriptedModel("near", "good"), tmp_path)
    first = json.loads((tmp_path / "attempt-1" / "attempt.json").read_text(encoding="utf-8"))
    assert first["script"] == "near"
    assert first["status"] == "fail"
    assert any(c["name"] == "title_boundary_setback" for c in first["checks"])
    summary = json.loads((tmp_path / "design.json").read_text(encoding="utf-8"))
    assert summary["accepted_attempt"] == 2
    assert [a["status"] for a in summary["attempts"]] == ["fail", "unknown"]


class SilentModel(ScriptedModel):
    """Replies without a script the first time, as a model sometimes does."""

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        if not self.seen:
            self.seen.append(list(conversation))
            raise ModelReplyError("The reply did not call run_blender_script.")
        return super().propose(conversation, allow_observations)


def test_a_reply_without_a_script_is_an_attempt_with_feedback(
    site: DesignSite, tmp_path: Path
) -> None:
    model = SilentModel("good")
    result = run(site, model, tmp_path)
    assert result.attempts[0].status == "error"
    assert "run_blender_script" in model.seen[1][-1].text
    assert result.accepted is result.attempts[1]


SLOPE = Observe("render_height_map", {"mode": "slope"})


def test_the_model_can_look_before_it_designs(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, "good")
    result = run(site, model, tmp_path)
    request, observation = model.seen[1][-2:]
    assert request.role == "request" and "render_height_map" in request.text
    assert observation.role == "observation" and "slope" in observation.text
    assert observation.image == tmp_path / "attempt-1" / "observation-1.png"
    assert observation.image is not None and observation.image.read_bytes().startswith(b"\x89PNG")
    assert result.attempts[0].observations == ("render_height_map",)
    trace = json.loads((tmp_path / "attempt-1" / "attempt.json").read_text(encoding="utf-8"))
    assert trace["observations"] == ["render_height_map"]
    assert result.accepted is result.attempts[0]


def test_once_the_budget_is_spent_the_model_must_design(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, SLOPE, "good")
    result = run(site, model, tmp_path)
    assert model.allowed == [True, True, False]
    assert "1 observation left" in model.seen[1][-1].text
    assert "0 observations left" in model.seen[2][-1].text
    assert result.attempts[0].observations == ("render_height_map", "render_height_map")
    assert result.accepted is result.attempts[0]


def test_a_request_over_the_budget_is_refused_not_fatal(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, SLOPE, SLOPE, "good")
    result = run(site, model, tmp_path)
    assert "No observations left" in model.seen[3][-1].text
    assert result.attempts[0].observations == ("render_height_map", "render_height_map")
    assert result.accepted is result.attempts[0]


def test_a_model_that_never_designs_loses_the_attempt(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(*[SLOPE] * 5, "good")
    result = run(site, model, tmp_path)
    first, second = result.attempts
    assert first.status == "error" and "observation" in first.feedback
    assert result.accepted is second


def test_observations_can_be_switched_off(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, "good")
    result = run(site, model, tmp_path, allow_observations=False)
    assert model.allowed == [False, False]
    assert "not available" in model.seen[1][-1].text
    assert result.attempts[0].observations == ()
    assert result.accepted is result.attempts[0]


def test_a_proposal_the_evaluator_rejects_is_fed_back(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("off", "good")
    result = run(site, model, tmp_path)
    assert result.attempts[0].status == "error"
    assert "terrain" in model.seen[1][-1].text
    assert result.accepted is result.attempts[1]


def test_each_attempt_is_reported_as_it_finishes(site: DesignSite, tmp_path: Path) -> None:
    seen: list[int] = []
    model = ScriptedModel("near", "good")
    result = design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        runner=fake_runner,
        on_attempt=lambda attempt: seen.append(attempt.number),
    )
    assert seen == [1, 2]
    assert [a.number for a in result.attempts] == seen


def test_a_stale_render_is_never_fed_back(site: DesignSite, tmp_path: Path) -> None:
    """Reusing a runs directory must not show the model an old run's picture."""
    (tmp_path / "attempt-1").mkdir()
    (tmp_path / "attempt-1" / "design.png").write_bytes(b"old")
    model = SilentModel("good")
    run(site, model, tmp_path)
    assert model.seen[1][-1].image is None


def test_a_revision_continues_from_the_design_it_changes(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("good")
    before = Revision(
        script="near", feedback="Evaluator verdict: fail.", instructions=("Move it east.",)
    )
    result = design(
        "Add a small dwelling.", site, model, tmp_path, runner=fake_runner, revising=before
    )
    roles = [t.role for t in model.seen[0]]
    assert roles == ["system", "user", "design", "feedback", "user"]
    assert model.seen[0][2].text == "near" and model.seen[0][4].text == "Move it east."
    assert result.accepted is result.attempts[0]


def test_the_model_is_told_where_to_keep_clear(site: DesignSite, tmp_path: Path) -> None:
    """Preservation areas and listed buildings are in the prompt, in local coordinates."""
    garden: Ring = ((10.0, 2.0), (14.0, 2.0), (14.0, 6.0), (10.0, 6.0), (10.0, 2.0))
    house: Ring = ((30.0, 12.0), (36.0, 12.0), (36.0, 18.0), (30.0, 18.0), (30.0, 12.0))
    context = replace(site.context, preservation_areas=(garden,), confirmed_buildings=(house,))
    model = ScriptedModel("good")
    run(replace(site, context=context), model, tmp_path)
    prompt = model.seen[0][0].text
    assert "kept clear" in prompt and "(10.00, 2.00)" in prompt
    assert "existing buildings" in prompt and "(30.00, 12.00)" in prompt


def test_earlier_changes_are_already_built_and_only_the_latest_is_asked_for() -> None:
    """The revised script already includes the earlier changes: asking for them
    again would apply a relative change ("3 m further back") twice."""
    request = Revision("s", "f", ("Move it 3 m further back.", "Make it bigger.")).request
    already, now = request.split("Now:")
    assert "already includes" in already and "Move it 3 m further back." in already
    assert "Make it bigger." in now and "Move it" not in now
    assert Revision("s", "f", ("Make it bigger.",)).request == "Make it bigger."
