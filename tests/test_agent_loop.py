"""Tests for button_nz.agent.loop with a scripted model and a fake Blender runner."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.conversation import ModelReplyError
from button_nz.agent.loop import DesignResult, DesignSite, Turn, design
from button_nz.blender_worker.run import DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.evaluation import SiteContext, Status
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# One 40 m x 20 m parcel; the local frame's origin is NZTM (0, 0), datum 100 m.
PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
GOOD = {
    "faces_xy": [rect(15, 7, 21, 12)],
    "z_min": 0.3,
    "z_max": 3.9,
    "floor_area_m2": 26.0,
    "storeys": 1,
}
NEAR = GOOD | {"faces_xy": [rect(0.5, 7, 6.5, 12)]}  # 0.5 m from the title boundary
BROKEN = {"error": 'Traceback (most recent call last):\n  File "design.py", line 1\nNameError: x'}
MEASURED = {"good": GOOD, "near": NEAR, "broken": BROKEN}


@pytest.fixture
def site() -> DesignSite:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    scene = scene_input(grid, frame, [PARCEL])
    return DesignSite(scene, frame, SiteContext(parcels=(PARCEL,), terrain=grid))


class ScriptedModel:
    """Replays scripts in order and records every conversation it was shown."""

    def __init__(self, *scripts: str) -> None:
        self.scripts = list(scripts)
        self.seen: list[list[Turn]] = []

    def propose(self, conversation: Sequence[Turn]) -> str:
        self.seen.append(list(conversation))
        return self.scripts.pop(0)


def fake_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    out_dir.mkdir(parents=True, exist_ok=True)
    measurements = {"error": None} | MEASURED[script.strip()]
    png = out_dir / "design.png"
    png.write_bytes(b"png")
    failed = measurements.get("error") is not None
    return DesignOutputs(measurements, out_dir / "design.py", None, None if failed else png)


def run(site: DesignSite, model: ScriptedModel, tmp_path: Path, attempts: int = 3) -> DesignResult:
    return design("Add a small dwelling.", site, model, tmp_path, attempts, runner=fake_runner)


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

    def propose(self, conversation: Sequence[Turn]) -> str:
        if not self.seen:
            self.seen.append(list(conversation))
            raise ModelReplyError("The reply did not call run_blender_script.")
        return super().propose(conversation)


def test_a_reply_without_a_script_is_an_attempt_with_feedback(
    site: DesignSite, tmp_path: Path
) -> None:
    model = SilentModel("good")
    result = run(site, model, tmp_path)
    assert result.attempts[0].status == "error"
    assert "run_blender_script" in model.seen[1][-1].text
    assert result.accepted is result.attempts[1]
