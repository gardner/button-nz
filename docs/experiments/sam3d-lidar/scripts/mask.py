"""Building mask from the ray-cast: pixels whose surface point lies inside the LINZ outline
(buffered for the 1 m DSM's sloped walls), stands above the ground and isn't vegetation.
Also checks the pointmap.

usage: mask.py SCENE_DIR POINTS_NPZ
POINTS_NPZ: split.py's points.npz; only its training points are read.
A surface point is vegetation if its nearest training point is classed as vegetation
(LINZ classes 3-5), or if it is more than ROOF_TOLERANCE_M above the highest
building-class training point inside the outline: tree canopy over the roof, much of
which LINZ leaves unclassified (class 1).
Writes mask.png, mask_overlay.png, pointmap_cv.npy (H,W,3 float32, OpenCV camera coords, metres).
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape
from shapely.affinity import translate

WALL_BUFFER_M = 1.0  # the DSM is 1 m: its walls lean out by up to a cell
MIN_HEIGHT_M = 1.0
VEGETATION = (3, 4, 5)  # LINZ: low, medium and high vegetation
BUILDING = 6
ROOF_TOLERANCE_M = 0.5


def vegetation(hits: np.ndarray, train: np.ndarray, roof_top: float) -> np.ndarray:
    """True for each surface point (N,3) that is tree or shrub, from the training points (M,4)."""
    _, nearest = cKDTree(train[:, :3]).query(hits)
    return np.isin(train[nearest, 3], VEGETATION) | (hits[:, 2] > roof_top + ROOF_TOLERANCE_M)


def main(scene_dir: Path, points_npz: Path) -> None:
    rc = np.load(scene_dir / "raycast.npz")
    scene = np.load(scene_dir / "scene.npz")
    meta = json.loads((scene_dir / "outline.json").read_text())
    cx, cy = meta["origin_nztm"]
    outline = translate(shape(meta["target"]), -cx, -cy)
    world, cam_cv, K = rc["world"], rc["cam_cv"], rc["K"]
    h, w, _ = world.shape

    # check 1: projecting each hit back through K lands on its own pixel
    z = cam_cv[..., 2]
    u = K[0, 0] * cam_cv[..., 0] / z + K[0, 2]
    v = K[1, 1] * cam_cv[..., 1] / z + K[1, 2]
    uu, vv = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    err = np.nanmax(np.hypot(u - uu, v - vv))
    # check 2: hits lie on the DSM surface
    dsm, dem, cell = scene["dsm"], scene["dem"], float(scene["cell"])
    west, _, _, north = scene["bbox_local"]
    col = np.clip(((world[..., 0] - west) / cell - 0.5).round(), 0, dsm.shape[1] - 1)
    row = np.clip(((north - world[..., 1]) / cell - 0.5).round(), 0, dsm.shape[0] - 1)
    ok = np.isfinite(world[..., 0])
    r, c = row[ok].astype(int), col[ok].astype(int)
    dz = np.abs(world[..., 2][ok] - dsm[r, c])
    print(f"reprojection max err {err:.4f} px; |hit z - DSM| median {np.median(dz):.3f} p99 {np.percentile(dz, 99):.3f} m")

    ndsm = np.full((h, w), np.nan)
    ndsm[ok] = world[..., 2][ok] - dem[r, c]
    inside = np.zeros((h, w), bool)
    inside[ok] = contains_xy(outline.buffer(WALL_BUFFER_M), world[..., 0][ok], world[..., 1][ok])
    mask = inside & (np.nan_to_num(ndsm) > MIN_HEIGHT_M)
    train = np.load(points_npz)["train"].astype(float)
    train[:, 0] -= cx
    train[:, 1] -= cy
    on_roof = contains_xy(outline, train[:, 0], train[:, 1]) & (train[:, 3] == BUILDING)
    roof_top = float(train[on_roof, 2].max())
    veg = vegetation(world[mask], train, roof_top)
    print(f"above ground in the outline {mask.sum()} px; vegetation {veg.sum()} px "
          f"(roof top {roof_top:.2f} m)")
    mask[mask] = ~veg
    Image.fromarray((mask * 255).astype(np.uint8)).save(scene_dir / "mask.png")
    rgb = np.asarray(Image.open(scene_dir / "oblique.png").convert("RGB")).astype(float)
    rgb[mask] = 0.5 * rgb[mask] + 0.5 * np.array([255, 0, 0])
    Image.fromarray(rgb.astype(np.uint8)).save(scene_dir / "mask_overlay.png")
    np.save(scene_dir / "pointmap_cv.npy", cam_cv.astype(np.float32))
    print(f"mask {mask.mean():.3f} of image, {mask.sum()} px")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
