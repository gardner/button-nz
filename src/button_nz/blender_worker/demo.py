"""Build the demo site's terrain scene: ``uv run python -m button_nz.blender_worker.demo OUT_DIR``.

Reads the DEM and DSM windows pinned in ``data/demo-site`` from LINZ's public
S3, centres a local frame on the site, and builds the scene in headless Blender.
"""

import sys
from pathlib import Path

from button_nz.blender_worker.run import SceneOutputs, build_scene
from button_nz.blender_worker.scene_input import scene_input
from button_nz.demo_site import load_demo_site
from button_nz.geo.crs import LocalFrame
from button_nz.geo.terrain import read_terrain


def build_demo_scene(out_dir: Path, margin_m: float = 20.0) -> SceneOutputs:
    site = load_demo_site()
    grid = read_terrain(
        site.rasters["dem"].asset, site.rasters["dsm"].asset, site.extent_nztm, margin_m
    )
    frame = LocalFrame.centred_on(site.extent_nztm)
    scene = scene_input(grid, frame, [parcel.ring for parcel in site.parcels])
    return build_scene(scene, out_dir)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit(f"usage: {argv[0]} OUT_DIR")
    out = build_demo_scene(Path(argv[1]))
    print(f"{out.glb}\n{out.png}")


if __name__ == "__main__":
    main(sys.argv)
