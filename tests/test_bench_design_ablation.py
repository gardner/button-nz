"""Tests for button_nz.bench.design_ablation: Experiment C's runs and report."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.conversation import Observe, Turn
from button_nz.agent.site import DesignSite
from button_nz.bench.design_ablation import CONDITIONS, RunResult, report, run, summarise
from button_nz.blender_worker.run import BlenderError, DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid
from meshes import box

PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
GOOD = {"triangles": box(15, 7, 0.3, 21, 12, 3.9), "floor_area_m2": 26.0, "storeys": 1}
NEAR = GOOD | {"triangles": box(0.5, 7, 0.3, 6.5, 12, 3.9)}  # 0.5 m from the boundary
OFF = GOOD | {"triangles": box(38, 7, 0.3, 44, 12, 3.9)}  # past the terrain: rejected
MEASURED = {"good": GOOD, "near": NEAR, "off": OFF, "broken": {"error": "NameError: x"}}


@pytest.fixture
def site() -> DesignSite:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    return DesignSite(
        scene_input(grid, frame, [PARCEL]), frame, SiteContext(parcels=(PARCEL,), terrain=grid)
    )


def fake_runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
    out_dir.mkdir(parents=True, exist_ok=True)
    measurements = {"error": None} | MEASURED[script]
    return DesignOutputs(measurements, out_dir / "design.py", None, None)


class Scripted:
    """Replies "near" first, then "good" after evaluator feedback names the setback."""

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        self.calls += 1
        if allow_observations and not any(t.role == "observation" for t in conversation):
            return Observe("render_height_map", {"mode": "slope"})
        told = [t.text for t in conversation if t.role == "feedback"]
        return "good" if any("setback" in text for text in told) else "near"


def test_each_condition_is_run_and_logged(site: DesignSite, tmp_path: Path) -> None:
    results = run(["A studio."], CONDITIONS, 1, site, Scripted(), tmp_path, fake_runner)
    by_name = {r.condition: r for r in results}
    assert set(by_name) == {"one_shot", "errors", "evaluator", "evaluator_lidar"}
    assert by_name["one_shot"].attempts == 1 and not by_name["one_shot"].accepted
    assert by_name["errors"].attempts == 1 and not by_name["errors"].accepted  # it ran: done
    assert by_name["evaluator"].repaired and by_name["evaluator"].attempts == 2
    assert by_name["evaluator_lidar"].observations >= 1 and by_name["evaluator_lidar"].accepted
    assert by_name["evaluator"].verdicts == ("fail", "unknown")
    lines = (tmp_path / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and json.loads(lines[0])["condition"] == "one_shot"


def test_a_run_that_cannot_complete_is_recorded_not_dropped(
    site: DesignSite, tmp_path: Path
) -> None:
    def no_gpu(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
        raise BlenderError("no GPU available to Cycles")

    (result,) = run(["A studio."], CONDITIONS[:1], 1, site, Scripted(), tmp_path, no_gpu)
    assert result.error is not None and "no GPU" in result.error
    assert result.seconds > 0.0  # the time it took to fail is still measured
    assert not result.accepted


def test_attempts_that_finished_before_a_failure_are_kept(site: DesignSite, tmp_path: Path) -> None:
    """Blender fails on attempt 2: attempt 1 ran and was judged, and says so."""

    def fails_second(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
        if out_dir.name == "attempt-2":
            raise BlenderError("no GPU available to Cycles")
        return fake_runner(scene, script, out_dir)

    evaluator = [c for c in CONDITIONS if c.name == "evaluator"]
    (result,) = run(["A studio."], evaluator, 1, site, Scripted(), tmp_path, fails_second)
    assert result.error is not None and "no GPU" in result.error
    assert result.attempts == 1 and result.executed == 1 and result.verdicts == ("fail",)
    assert not result.accepted


def _result(condition: str, accepted: bool, repaired: bool, verdicts: tuple[str, ...]) -> RunResult:
    executed = sum(v != "error" for v in verdicts)
    return RunResult(
        0, condition, 0, len(verdicts), executed, accepted, repaired, 0, verdicts, 10.0, None
    )


def test_the_summary_rates() -> None:
    results = [
        _result("evaluator", True, True, ("fail", "pass")),
        _result("evaluator", False, False, ("error", "fail", "fail")),
        _result("evaluator", True, False, ("pass",)),
    ]
    s = summarise(results)["evaluator"]
    assert s["runs"] == 3
    assert s["accepted"] == 2
    assert s["execution_rate"] == pytest.approx(5 / 6)
    assert s["repair_rate"] == pytest.approx(1 / 2)  # of the 2 runs whose first attempt failed
    assert s["mean_attempts"] == pytest.approx(2.0)


def test_the_report_states_method_and_sample_sizes() -> None:
    results = [
        _result("one_shot", False, False, ("fail",)),
        _result("evaluator", True, True, ("fail", "pass")),
    ]
    text = report(results, {"model": "muse-spark-1.3", "briefs": 1, "repeats": 1})
    assert "muse-spark-1.3" in text
    assert "| one_shot | 1 | 0 (0%) |" in text
    assert "| evaluator | 1 | 1 (100%) |" in text
    assert "a script that runs ends the run" in text  # what `errors` measures


class Always:
    def __init__(self, script: str) -> None:
        self.script = script

    def propose(self, conversation: Sequence[Turn], allow_observations: bool) -> str | Observe:
        return self.script


def test_an_attempt_the_evaluator_rejected_still_executed(site: DesignSite, tmp_path: Path) -> None:
    """Built and measured, then rejected (off the terrain): it ran, and is labelled so."""
    off, broke = tmp_path / "off", tmp_path / "broken"
    (result,) = run(["A studio."], CONDITIONS[:1], 1, site, Always("off"), off, fake_runner)
    assert result.executed == 1
    assert result.verdicts == ("rejected",)
    (broken,) = run(["A studio."], CONDITIONS[:1], 1, site, Always("broken"), broke, fake_runner)
    assert broken.executed == 0 and broken.verdicts == ("error",)


def test_an_output_directory_holds_one_run(site: DesignSite, tmp_path: Path) -> None:
    run(["A studio."], CONDITIONS[:1], 1, site, Always("good"), tmp_path, fake_runner)
    with pytest.raises(FileExistsError, match="already"):
        run(["A studio."], CONDITIONS[:1], 1, site, Always("good"), tmp_path, fake_runner)
