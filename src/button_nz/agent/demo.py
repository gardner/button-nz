"""Run the design loop on the demo site with Muse:

    MODEL_API_KEY=... uv run python -m button_nz.agent.demo RUNS_DIR "brief"

Reads the DEM/DSM pinned in data/demo-site, builds the site scene, and lets the
model design, with each attempt built in sandboxed Blender and checked by the
independent evaluator. Every attempt is kept under RUNS_DIR.
"""

import sys
from pathlib import Path

from button_nz.agent.conversation import Model
from button_nz.agent.loop import DesignResult, DesignSite, design
from button_nz.agent.model import ChatModel
from button_nz.blender_worker.scene_input import scene_input
from button_nz.demo_site import load_demo_site
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import read_terrain

BRIEF = (
    "I want to add a small one-bedroom prefab dwelling. Keep as much of the existing "
    "garden and trees as possible and avoid unnecessary earthworks."
)


def demo_site(margin_m: float = 20.0) -> DesignSite:
    site = load_demo_site()
    grid = read_terrain(
        site.rasters["dem"].asset, site.rasters["dsm"].asset, site.extent_nztm, margin_m
    )
    frame = LocalFrame.centred_on(site.extent_nztm)
    parcels = tuple(parcel.ring for parcel in site.parcels)
    return DesignSite(
        scene_input(grid, frame, parcels), frame, SiteContext(parcels=parcels, terrain=grid)
    )


def run(runs_dir: Path, brief: str = BRIEF, model: Model | None = None) -> DesignResult:
    return design(brief, demo_site(), model or ChatModel.from_env(), runs_dir)


def main(argv: list[str]) -> None:
    if len(argv) not in (2, 3):
        raise SystemExit(f'usage: {argv[0]} RUNS_DIR ["brief"]')
    result = run(Path(argv[1]), argv[2] if len(argv) == 3 else BRIEF)
    for attempt in result.attempts:
        print(f"attempt {attempt.number}: {attempt.status}")
    accepted = result.accepted
    print("accepted:", f"attempt {accepted.number}" if accepted else "none")


if __name__ == "__main__":
    main(sys.argv)
