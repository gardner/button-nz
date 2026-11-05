"""Tests for the instant massing (#188): as a design starts, its live state
says where a home of its plan fits, solved and checked before Muse has said
anything; and when its step began and its newest view was made."""

import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from button_nz.agent.loop import DesignSite
from button_nz.agent.placement import PROMPT_EAVES_M, solve
from button_nz.api.massing import lonlat_ring
from button_nz.blender_worker.run import DesignOutputs
from button_nz.blender_worker.scene_input import SceneInput, scene_input
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import TerrainGrid
from test_api import ScriptedModel, Service, fake_runner, synthetic_site
from test_api_place import Placing


class Watched:
    """The job's ``live`` as seen from inside each Blender run."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []
        self.look: Any = None

    def runner(self, scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
        self.seen.append(self.look())
        return fake_runner(scene, script, out_dir)


def _watched_service(tmp_path: Path, **kwargs: Any) -> tuple[Service, Watched, str]:
    watched = Watched()
    service = Service(tmp_path, runner=watched.runner, **kwargs)
    job_id = service.queue()
    watched.look = lambda: service.client.get(f"/designs/{job_id}").json()["live"]
    return service, watched, job_id


def test_a_running_bespoke_design_shows_where_its_first_plan_fits(tmp_path: Path) -> None:
    service, watched, _ = _watched_service(tmp_path)
    service.worker.run_next()
    placement = watched.seen[0]["placement"]
    (best,) = solve(synthetic_site().context, 10.0, 7.0, PROMPT_EAVES_M, 1).placements
    assert placement["plan"] == {"length_m": 10.0, "width_m": 7.0, "eaves_m": PROMPT_EAVES_M}
    assert placement["walls"] == lonlat_ring(best.walls)  # lon/lat, as the site's layers are
    assert placement["outline"] == lonlat_ring(best.outline)
    assert placement["clearances"] == {
        k: pytest.approx(v, abs=1e-3) for k, v in best.clearances.items()
    }
    assert placement["clearances"]["title_boundary_m"] >= 2.0
    assert placement["floor_range_m"] == pytest.approx(list(best.floor_range_m), abs=1e-3)
    assert 0 <= placement["found_in_s"] < 1.0  # in well under a second


def _narrow_site() -> DesignSite:
    """A 40 x 11 m title: 7 m of room between its 2 m setbacks, too narrow for
    a 10 x 7 m plan's 11.2 x 8.2 m outline, wide enough for an 11 x 5 m one's."""
    ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 11.0), (0.0, 11.0), (0.0, 0.0))
    dem = np.full((11, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 11.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    return DesignSite(
        scene_input(grid, frame, [ring]), frame, SiteContext(parcels=(ring,), terrain=grid)
    )


def test_a_bespoke_design_shows_the_first_plan_that_places(tmp_path: Path) -> None:
    site = _narrow_site()
    assert not solve(site.context, 10.0, 7.0, PROMPT_EAVES_M, 1).placements
    service, watched, _ = _watched_service(tmp_path, site=lambda: site)
    service.worker.run_next()
    assert watched.seen[0]["placement"]["plan"]["length_m"] == 11.0


def test_where_no_plan_places_there_is_no_massing(tmp_path: Path) -> None:
    service, watched, _ = _watched_service(tmp_path, site=_tiny_site)
    service.worker.run_next()
    assert watched.seen[0]["placement"] is None


def _tiny_site() -> DesignSite:
    ring = ((0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0), (0.0, 0.0))
    dem = np.full((8, 8), 100.0)
    grid = TerrainGrid((0.0, 0.0, 8.0, 8.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame(origin=(0.0, 0.0))
    return DesignSite(
        scene_input(grid, frame, [ring]), frame, SiteContext(parcels=(ring,), terrain=grid)
    )


def test_a_placed_product_shows_where_its_footprint_fits(tmp_path: Path) -> None:
    placing = Placing(tmp_path, "good")
    seen: list[dict[str, Any]] = []
    job_id = placing.place("long").json()["id"]
    run = placing.run

    def watching(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
        seen.append(placing.client.get(f"/designs/{job_id}").json()["live"])
        return run(scene, script, out_dir)

    placing.worker.runner = watching
    placing.worker.run_next()
    assert seen[0]["placement"]["plan"] == {
        "length_m": 8.0,
        "width_m": 4.0,
        "eaves_m": PROMPT_EAVES_M,
    }


def test_a_revision_shows_no_new_massing(tmp_path: Path) -> None:
    """It starts from its parent's design, already on the map."""
    model = ScriptedModel("good", "good")
    service, watched, parent = _watched_service(tmp_path, model=lambda: model)
    service.worker.run_next()
    child = service.client.post(
        f"/designs/{parent}/revisions", json={"instruction": "Turn it."}
    ).json()["id"]
    watched.look = lambda: service.client.get(f"/designs/{child}").json()["live"]
    service.worker.run_next()
    assert watched.seen[-1]["placement"] is None


def test_the_live_state_says_how_long_its_step_and_newest_view_have_been_there(
    tmp_path: Path,
) -> None:
    """Ages, not times: the browser's clock needn't agree with the server's."""
    service = Service(tmp_path)
    seen: list[dict[str, Any]] = []

    def runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
        newest = out_dir / "observation-4.png"  # the brief's last view
        made = time.time() - 60
        os.utime(newest, (made, made))  # made a minute ago
        seen.append(service.client.get(f"/designs/{job_id}").json()["live"])
        return fake_runner(scene, script, out_dir)

    service.worker.runner = runner
    job_id = service.queue()
    service.worker.run_next()
    live = seen[0]
    assert 0 <= live["step_s"] < 5  # rendering began just now
    assert 60 <= live["newest_view_s"] < 65
    assert "since" not in live and "newest_view_at" not in live


def test_a_step_with_no_views_yet_has_no_newest_view_age(tmp_path: Path) -> None:
    service = Service(tmp_path)
    seen: list[dict[str, Any]] = []

    def runner(scene: SceneInput, script: str, out_dir: Path) -> DesignOutputs:
        for view in out_dir.glob("observation-*.png"):
            view.unlink()
        seen.append(service.client.get(f"/designs/{job_id}").json()["live"])
        return fake_runner(scene, script, out_dir)

    service.worker.runner = runner
    job_id = service.queue()
    service.worker.run_next()
    assert seen[0]["observations"] == [] and seen[0]["newest_view_s"] is None
