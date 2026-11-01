"""How good is the monocular pointmap SAM 3D would use without LiDAR? MoGe on the oblique vs the
ray-cast LiDAR pointmap.

usage: CUDA_VISIBLE_DEVICES=1 HF_HOME=... python -I moge_check.py SCENE_DIR [MODEL]
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch
from moge.model.v1 import MoGeModel
from PIL import Image

scene_dir = Path(sys.argv[1])
model_id = sys.argv[2] if len(sys.argv) > 2 else "Ruicheng/moge-vitl"


def site_points(cam_cv: np.ndarray, cam_to_world: np.ndarray) -> np.ndarray:
    cam_bl = cam_cv * np.array([1.0, -1.0, -1.0])
    return cam_bl @ cam_to_world[:3, :3].T + cam_to_world[:3, 3]


def main() -> None:
    image = np.asarray(Image.open(scene_dir / "oblique.png").convert("RGB"))
    mask = np.asarray(Image.open(scene_dir / "mask.png")) > 127
    rc = np.load(scene_dir / "raycast.npz")
    lidar = rc["cam_cv"]
    model = MoGeModel.from_pretrained(model_id).cuda().eval()
    with torch.no_grad():
        out = model.infer(torch.from_numpy(image).float().div(255).permute(2, 0, 1).cuda(), force_projection=False)
    moge = out["points"].cpu().numpy()
    valid = np.isfinite(moge).all(-1) & np.isfinite(lidar).all(-1)
    m = mask & valid
    scale = float(np.median(lidar[m][:, 2] / moge[m][:, 2]))  # MoGe-1 is scale-free
    moge_s = moge * scale
    abs_rel = lambda sel: float(np.median(np.abs(moge_s[sel][:, 2] - lidar[sel][:, 2]) / lidar[sel][:, 2]))
    err3d = np.linalg.norm(moge_s[m] - lidar[m], axis=1)
    fx_moge = float(out["intrinsics"][0, 0].cpu()) * image.shape[1] if "intrinsics" in out else float("nan")
    w_l, w_m = site_points(lidar, rc["cam_to_world"]), site_points(moge_s, rc["cam_to_world"])
    np.save(scene_dir / "moge_points_cv_scaled.npy", moge_s.astype(np.float32))

    def height(world: np.ndarray) -> float:
        z = world[m][:, 2]
        return float(np.percentile(z, 98) - np.percentile(w_l[valid & ~mask][:, 2], 2))

    result = {
        "model": model_id,
        "scale_to_metric": scale,
        "metric_scale_raw_moge_median_depth_m": float(np.median(moge[m][:, 2])),
        "lidar_median_depth_m": float(np.median(lidar[m][:, 2])),
        "absrel_mask": abs_rel(m),
        "absrel_image": abs_rel(valid),
        "err3d_mask_m_median": float(np.median(err3d)),
        "err3d_mask_m_p90": float(np.percentile(err3d, 90)),
        "fx_true_px": float(rc["K"][0, 0]),
        "fx_moge_px": fx_moge,
        "roof_top_above_scene_min_lidar_m": height(w_l),
        "roof_top_above_scene_min_moge_m": height(w_m),
    }
    (scene_dir / "moge_check.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    dl = np.where(valid, lidar[..., 2], np.nan)
    dm = np.where(valid, moge_s[..., 2], np.nan)
    lo, hi = np.nanpercentile(dl, 1), np.nanpercentile(dl, 99)
    vis = lambda d: (255 * np.clip((d - lo) / (hi - lo), 0, 1)).astype(np.uint8)
    rel = np.clip(np.abs(dm - dl) / dl / 0.2, 0, 1)
    Image.fromarray(np.concatenate([vis(dl), vis(dm), (255 * rel).astype(np.uint8)], axis=1)).save(
        scene_dir / "depth_lidar_moge_err.png"
    )


if __name__ == "__main__":
    main()
