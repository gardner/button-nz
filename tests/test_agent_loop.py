"""Tests for button_nz.agent.loop with a scripted model and a fake Blender runner."""

import json
import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.conversation import ModelReplyError, Observe
from button_nz.agent.loop import DesignResult, DesignSite, Phase, Revision, Step, Turn, design
from button_nz.blender_worker.run import DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.evaluation import Footprint, SiteContext, Status
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.sites.frontages import Frontage
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
SPLIT = GOOD | {  # two separate boxes: rendered, then refused by the contract
    "triangles": box(15, 7, 0.3, 18, 12, 3.9) + box(20, 7, 0.3, 23, 12, 3.9)
}
MEASURED = {"good": GOOD, "near": NEAR, "broken": BROKEN, "off": OFF_TERRAIN, "split": SPLIT}


def flat_site() -> DesignSite:
    """The 40 m x 20 m parcel on flat ground at 100 m."""
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    scene = scene_input(grid, frame, [PARCEL])
    return DesignSite(scene, frame, SiteContext(parcels=(PARCEL,), terrain=grid))


@pytest.fixture
def site() -> DesignSite:
    return flat_site()


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
    system, brief, *_views = model.seen[0]
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
VIEWS = ("render_hillshade", "render_contours", "render_height_map", "render_cross_section")
# The flat site's room has one rectangle 3 m wide or more; then the whole room.
GIVEN = (*VIEWS, "inspect_elevation", "inspect_elevation")


def test_the_standard_views_come_with_the_brief(site: DesignSite, tmp_path: Path) -> None:
    """Muse sees the site before its first move, without asking: the views and
    the ground's numbers are recorded as attempt 1's first observations, files
    and all."""
    model = ScriptedModel("good")
    result = run(site, model, tmp_path)
    _, brief, *views = model.seen[0]
    assert [t.role for t in views] == ["view"] * len(GIVEN)
    folder = tmp_path / "attempt-1"
    images = [folder / f"observation-{k}.png" for k in range(1, 5)]
    assert [t.image for t in views] == [*images, None, None]  # the numbers are text
    assert all(image.read_bytes().startswith(b"\x89PNG") for image in images)
    assert "Hillshade" in views[0].text and "Terrain profile" in views[3].text
    assert "largest rectangle 1" in views[4].text and "whole room" in views[5].text
    assert "2 more" in brief.text  # the budget is still the model's own
    assert result.attempts[0].observations == GIVEN
    trace = json.loads((folder / "attempt.json").read_text(encoding="utf-8"))
    assert trace["observations"] == list(GIVEN)
    assert trace["observations_given"] == len(GIVEN)


def test_the_views_are_given_once_and_kept(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("near", "good")
    result = run(site, model, tmp_path)
    assert [t.role for t in model.seen[1]].count("view") == len(GIVEN)  # still there
    assert result.attempts[1].observations == ()
    assert not list((tmp_path / "attempt-2").glob("observation-*.png"))
    trace = json.loads((tmp_path / "attempt-2" / "attempt.json").read_text(encoding="utf-8"))
    assert trace["observations_given"] == 0


def test_without_observations_no_views_are_given(site: DesignSite, tmp_path: Path) -> None:
    """Experiment C's conditions without the LiDAR stay without it."""
    model = ScriptedModel("good")
    run(site, model, tmp_path, allow_observations=False)
    assert [t.role for t in model.seen[0]] == ["system", "user"]
    assert "With this brief" not in model.seen[0][1].text


def test_the_model_can_look_before_it_designs(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, "good")
    result = run(site, model, tmp_path)
    request, observation = model.seen[1][-2:]
    assert request.role == "request" and "render_height_map" in request.text
    assert observation.role == "observation" and "slope" in observation.text
    # Numbered after the observations given with the brief.
    assert observation.image == tmp_path / "attempt-1" / "observation-7.png"
    assert observation.image is not None and observation.image.read_bytes().startswith(b"\x89PNG")
    assert result.attempts[0].observations == (*GIVEN, "render_height_map")
    trace = json.loads((tmp_path / "attempt-1" / "attempt.json").read_text(encoding="utf-8"))
    assert trace["observations"] == [*GIVEN, "render_height_map"]
    assert result.accepted is result.attempts[0]


def test_once_the_budget_is_spent_the_model_must_design(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, SLOPE, "good")
    result = run(site, model, tmp_path)
    assert model.allowed == [True, True, False]
    assert "1 observation left" in model.seen[1][-1].text
    assert "0 observations left" in model.seen[2][-1].text
    assert result.attempts[0].observations == (*GIVEN, "render_height_map", "render_height_map")
    assert result.accepted is result.attempts[0]


def test_a_request_over_the_budget_is_refused_not_fatal(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel(SLOPE, SLOPE, SLOPE, "good")
    result = run(site, model, tmp_path)
    assert "No observations left" in model.seen[3][-1].text
    assert result.attempts[0].observations == (*GIVEN, "render_height_map", "render_height_map")
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
    assert not list((tmp_path / "attempt-1").glob("observation-*.png"))
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


def test_without_evaluator_feedback_only_execution_errors_earn_another_attempt(
    site: DesignSite, tmp_path: Path
) -> None:
    """Experiment C's execution-errors-only condition: an error comes back, but a
    script that ran ends the run. Retrying it would let the hidden verdict choose
    which runs get another draw; the evaluator still decides acceptance."""
    model = ScriptedModel("broken", "near", "good")
    result = design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        runner=fake_runner,
        allow_observations=False,
        evaluator_feedback=False,
    )
    assert "NameError" in model.seen[1][-1].text  # the execution error came back
    assert len(model.seen) == 2 and len(result.attempts) == 2  # "near" ran: the end
    assert "title_boundary_setback" in result.attempts[1].feedback  # recorded, not told
    assert result.accepted is None


def test_without_evaluator_feedback_a_contract_error_comes_back_without_the_render(
    site: DesignSite, tmp_path: Path
) -> None:
    """A dwelling in two pieces was rendered before the contract refused it: the
    error is an execution error and comes back, but the render is the evaluator
    condition's feedback, not this one's."""
    model = ScriptedModel("split", "good")
    design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        runner=fake_runner,
        allow_observations=False,
        evaluator_feedback=False,
    )
    told = model.seen[1][-1]
    assert told.role == "feedback" and "2 pieces" in told.text
    assert told.image is None


def test_without_evaluator_feedback_a_rejected_design_also_ends_the_run(
    site: DesignSite, tmp_path: Path
) -> None:
    """Off the terrain: built and measured, then rejected by the evaluator. It ran,
    so the model is not asked again (which would itself tell it the design failed)."""
    model = ScriptedModel("off", "good")
    result = design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        runner=fake_runner,
        allow_observations=False,
        evaluator_feedback=False,
    )
    assert len(model.seen) == 1 and len(result.attempts) == 1
    assert result.accepted is None


def test_a_revision_continues_from_the_design_it_changes(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("good")
    before = Revision(
        script="near", feedback="Evaluator verdict: fail.", instructions=("Move it east.",)
    )
    result = design(
        "Add a small dwelling.", site, model, tmp_path, runner=fake_runner, revising=before
    )
    roles = [t.role for t in model.seen[0]]
    assert roles == ["system", "user", *["view"] * len(GIVEN), "design", "feedback", "user"]
    assert model.seen[0][-3].text == "near" and model.seen[0][-1].text == "Move it east."
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


def test_each_step_is_reported_as_it_starts(site: DesignSite, tmp_path: Path) -> None:
    steps: list[Step] = []
    model = ScriptedModel(SLOPE, "near", "good")
    design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        3,
        runner=fake_runner,
        max_observations=2,
        on_step=steps.append,
    )
    assert [(s.attempt, s.phase, s.detail) for s in steps] == [
        (1, Phase.THINKING, ""),
        (1, Phase.OBSERVING, "render_height_map"),
        (1, Phase.THINKING, ""),
        (1, Phase.RENDERING, ""),
        (1, Phase.CHECKING, ""),
        (2, Phase.THINKING, ""),
        (2, Phase.RENDERING, ""),
        (2, Phase.CHECKING, ""),
    ]


def test_muse_is_told_the_road_frontages_and_which_is_the_street(
    site: DesignSite, tmp_path: Path
) -> None:
    coal = Frontage("Coal Street", True, (((0.0, 0.0), (40.0, 0.0)),))
    model = ScriptedModel("good")
    run(replace(site, frontages=(coal,)), model, tmp_path)
    contract = model.seen[0][0].text
    assert "facing Coal Street (the address's street)" in contract


def test_a_site_whose_frontages_arent_known_says_so(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("good")
    run(site, model, tmp_path)
    assert "road frontages: not known" in model.seen[0][0].text


def test_feedback_says_how_far_the_walls_are_from_each_road(
    site: DesignSite, tmp_path: Path
) -> None:
    coal = Frontage("Coal Street", True, (((0.0, 0.0), (40.0, 0.0)),))  # the south edge
    model = ScriptedModel("near", "good")
    result = run(replace(site, frontages=(coal,)), model, tmp_path)
    # GOOD's walls run from y = 7 to 12: 7 m from the south edge.
    assert "7.00 m from the Coal Street (the address's street) edge" in result.attempts[1].feedback


def test_muse_is_told_where_a_plain_rectangle_fits(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("good")
    run(site, model, tmp_path)
    contract = model.seen[0][0].text
    # The 40 x 20 m parcel, 2 m in from every side, on a 25 cm grid.
    assert re.search(r"1: 35\.\d x 15\.\d m", contract)
    assert "rather than cut a corner" in contract


def test_muse_is_asked_for_a_compact_plan_not_a_long_narrow_box(
    site: DesignSite, tmp_path: Path
) -> None:
    """The largest rectangle on a long section is long and narrow; filled, it
    looked out of place. A typical NZ cottage is at most about twice as long as wide."""
    model = ScriptedModel("good")
    run(site, model, tmp_path)
    contract = model.seen[0][0].text
    assert "at most about twice its width" in contract
    assert "not a size to fill" in contract


def test_the_compact_plan_gives_way_to_the_brief_and_a_narrow_room(
    site: DesignSite, tmp_path: Path
) -> None:
    """On a section 4 m wide a 60 m² brief can't be twice as long as wide; a brief
    may ask for a long plan outright."""
    model = ScriptedModel("good")
    run(site, model, tmp_path)
    contract = model.seen[0][0].text
    assert "unless the brief asks for that shape" in contract
    assert "too narrow for the brief's size at that proportion" in contract


def test_a_deck_is_suggested_where_it_suits_not_required(site: DesignSite, tmp_path: Path) -> None:
    model = ScriptedModel("good")
    run(site, model, tmp_path)
    contract = model.seen[0][0].text
    assert "Where the brief and the site suit one, add a deck" in contract
    assert "sunny (north) or living side" in contract
    assert "counts toward the setbacks" in contract
    assert "nothing below the floor's underside" in contract
    assert "can do without" in contract


def test_a_placed_product_keeps_its_footprint_without_the_compact_plan(
    site: DesignSite, tmp_path: Path
) -> None:
    """A real prefab's walls are fixed: it may be long and narrow."""
    model = ScriptedModel("good")
    product = Footprint("Long Cabin", 6.0, 5.0)
    design("Add it.", site, model, tmp_path, 1, runner=fake_runner, product=product)
    contract = model.seen[0][0].text
    assert "twice its width" not in contract
    assert "add a deck" in contract


def test_an_ask_says_which_observation_it_will_make(site: DesignSite, tmp_path: Path) -> None:
    """The ground's numbers given with the brief take numbers but make no file,
    so the next file's number can't be inferred from the files: the step says it."""
    steps: list[Step] = []
    model = ScriptedModel(SLOPE, "good")
    design(
        "Add a small dwelling.",
        site,
        model,
        tmp_path,
        runner=fake_runner,
        max_observations=2,
        on_step=steps.append,
    )
    (observing,) = [s for s in steps if s.phase is Phase.OBSERVING]
    assert observing.view == len(GIVEN) + 1
    assert (tmp_path / "attempt-1" / f"observation-{observing.view}.png").exists()
    assert all(s.view == 0 for s in steps if s.phase is not Phase.OBSERVING)
