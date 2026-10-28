"""The design loop end to end: real sandboxed Blender, real evaluator, and a
scripted model that revises after a failed check. Run with `pytest -m blender`."""

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from button_nz.agent.conversation import Turn
from button_nz.agent.loop import DesignSite, design
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext, Status
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender

# A 6 m x 5 m, 3.6 m tall dwelling whose floor sits 0.3 m above the ground.
DWELLING = """
bpy.ops.mesh.primitive_cube_add(size=1, location=({x}, 0.0, 0.3 + 1.8))
dwelling = bpy.context.active_object
dwelling.name = "Dwelling"
dwelling.scale = (6.0, 5.0, 3.6)
dwelling["floor_area_m2"] = 26.0
dwelling["storeys"] = 1
"""
TOO_CLOSE = DWELLING.format(x=-16.5)  # west wall 0.5 m from the title boundary
MOVED = DWELLING.format(x=0.0)


class RevisingModel:
    """Places the dwelling too close, then moves it once told the setback failed."""

    def __init__(self) -> None:
        self.feedback: list[str] = []

    def propose(self, conversation: Sequence[Turn]) -> str:
        if conversation[-1].role != "feedback":
            return TOO_CLOSE
        self.feedback.append(conversation[-1].text)
        return MOVED if "title_boundary_setback: fail" in conversation[-1].text else TOO_CLOSE


def test_a_failed_placement_is_revised_and_accepted(tmp_path: Path) -> None:
    dem = np.full((20, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 20.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    parcel: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    frame = LocalFrame.centred_on(grid.bbox)  # local x -20..20, y -10..10
    site = DesignSite(
        scene_input(grid, frame, [parcel]),
        frame,
        SiteContext(parcels=(parcel,), terrain=grid),
    )
    model = RevisingModel()

    result = design("A 26 m² studio.", site, model, tmp_path)

    first, second = result.attempts
    assert first.report is not None and first.report.status is Status.FAIL
    setback = next(c for c in first.report.checks if c.name == "title_boundary_setback")
    assert setback.measured["distance_m"] == pytest.approx(0.5, abs=1e-6)
    assert "0.50 m from the title boundary" in model.feedback[0]
    assert result.accepted is second
    assert second.report is not None
    statuses = {c.name: c.status for c in second.report.checks}
    assert statuses["title_boundary_setback"] is Status.PASS
    assert statuses["floor_level"] is Status.PASS  # floor 0.3 m above flat ground
    assert (tmp_path / "attempt-2" / "design.glb").is_file()
    summary = json.loads((tmp_path / "design.json").read_text(encoding="utf-8"))
    assert summary["accepted_attempt"] == 2


def test_the_demo_site_runs_through_the_loop(tmp_path: Path) -> None:
    """The real site (from LINZ's S3) with the scripted model: the wiring the
    Muse demo uses, minus the API key."""
    from button_nz.agent.demo import run

    result = run(tmp_path, "A small studio.", RevisingModel())
    assert result.attempts[0].report is not None
    by_name = {c.name: c for c in result.attempts[0].report.checks}
    assert 189.0 < by_name["floor_level"].measured["lowest_ground_m"] < 191.5
