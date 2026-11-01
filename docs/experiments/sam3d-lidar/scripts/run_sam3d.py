"""Run SAM 3D Objects on one virtual oblique, with and without the LiDAR pointmap.

usage (from the sam-3d-objects checkout, so its relative config paths resolve):
  CUDA_VISIBLE_DEVICES=1 python run_sam3d.py REPO_DIR SCENE_DIR [SEED]
Writes SCENE_DIR/{moge,lidar}/, all in the local site frame unless noted:
- mesh.npz: the mesh SAM 3D decodes from the same latent as its Gaussians
  (slat_decoder_mesh, output["mesh"][0]: vertices, faces), posed exactly as the
  Gaussians are. The model score.py scores, like Roofer's mesh.
- scene_points.npy: the Gaussian centres with each one's opacity (x, y, z,
  opacity); a secondary record, scored too.
- splat.ply (object frame), scene_points_p3d.npy (centres, PyTorch3D camera
  frame), pointmap_used.npy, stats.json (run stats and the pose).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

# OpenCV camera (x right, y down, z fwd) -> PyTorch3D camera (x left, y up, z fwd)
CV_TO_P3D = np.array([-1.0, -1.0, 1.0])
# PyTorch3D camera -> Blender camera (x right, y up, looking down -z)
P3D_TO_BLENDER = np.array([-1.0, 1.0, -1.0])


def to_site_frame(points_p3d: np.ndarray, cam_to_world: np.ndarray) -> np.ndarray:
    cam_bl = points_p3d * P3D_TO_BLENDER
    homog = np.concatenate([cam_bl, np.ones((len(cam_bl), 1))], axis=1)
    return (homog @ cam_to_world.T)[:, :3]


def object_to_site(points_local: torch.Tensor, output: dict, cam_to_world: np.ndarray) -> np.ndarray:
    """Object-frame points (the decoded mesh's vertices) into the site frame, by
    the same pose and the same call make_scene uses for the Gaussian centres."""
    from sam3d_objects.utils.visualization import SceneVisualizer

    scene = SceneVisualizer.object_pointcloud(
        points_local=points_local.unsqueeze(0),
        quat_l2c=output["rotation"],
        trans_l2c=output["translation"],
        scale_l2c=output["scale"],
    )
    return to_site_frame(scene.points_list()[0].detach().cpu().numpy(), cam_to_world)


def main(repo: Path, scene_dir: Path, seed: int) -> None:
    sys.path.insert(0, str(repo / "notebook"))
    from inference import Inference, make_scene

    image = np.asarray(Image.open(scene_dir / "oblique.png").convert("RGB"))
    mask = np.asarray(Image.open(scene_dir / "mask.png")) > 127
    rc = np.load(scene_dir / "raycast.npz")
    pointmap = torch.from_numpy((np.load(scene_dir / "pointmap_cv.npy") * CV_TO_P3D).astype(np.float32))

    t0 = time.time()
    inference = Inference(str(repo / "checkpoints/hf/pipeline.yaml"), compile=False)
    load_s = time.time() - t0
    for name, pm in (("moge", None), ("lidar", pointmap)):
        out_dir = scene_dir / name
        out_dir.mkdir(exist_ok=True)
        torch.cuda.reset_peak_memory_stats()
        t0 = time.time()
        output = inference(image, mask, seed=seed, pointmap=pm)
        run_s = time.time() - t0
        output["gs"].save_ply(str(out_dir / "splat.ply"))
        scene_gs = make_scene(output)
        pts = scene_gs.get_xyz.detach().cpu().numpy()
        np.save(out_dir / "scene_points_p3d.npy", pts)
        opacity = scene_gs.get_opacity.detach().cpu().numpy().reshape(-1, 1)
        # x, y, z, opacity: score.py keeps the active Gaussians (opacity > 0.9, SAM 3D's own cut)
        np.save(out_dir / "scene_points.npy", np.c_[to_site_frame(pts, rc["cam_to_world"]), opacity])
        mesh = output["mesh"][0]
        np.savez(out_dir / "mesh.npz", vertices=object_to_site(mesh.vertices.float(), output, rc["cam_to_world"]),
                 faces=mesh.faces.cpu().numpy().astype(np.int64))
        np.save(out_dir / "pointmap_used.npy", output["pointmap"].numpy())
        stats = {
            "seed": seed,
            "load_s": load_s,
            "run_s": run_s,
            "peak_gpu_gb": torch.cuda.max_memory_allocated() / 1e9,
            "n_gaussians": int(len(pts)),
            "mesh_vertices": int(len(mesh.vertices)),
            "mesh_faces": int(len(mesh.faces)),
            "scale": output["scale"].cpu().tolist(),
            "translation": output["translation"].cpu().tolist(),
            "rotation": output["rotation"].cpu().tolist(),
        }
        (out_dir / "stats.json").write_text(json.dumps(stats, indent=1))
        print(name, json.dumps({k: stats[k] for k in ("run_s", "peak_gpu_gb", "n_gaussians", "mesh_faces")}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 42)
