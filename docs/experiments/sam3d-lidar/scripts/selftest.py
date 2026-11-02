"""The scorer on known distortions of Roofer's b6 model, as points and as a mesh (#125).

usage: selftest.py SPIKE_DIR  (writes the distorted models to SPIKE_DIR/scores/selftest-*)

Shape must come out the same after alignment whatever the distortion, at any
scale and whether the model is points or a mesh; layout must catch each one.
Fails (AssertionError) if not.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))  # our own scorer, beside this
import score  # noqa: E402

R = Path(sys.argv[1])
meta = json.loads((R / "train-b6/outline.json").read_text())
v, f = score.cityjson_mesh(R / "roofer/out/objects/b6/reconstruct/b6.city.jsonl", tuple(meta["origin_nztm"]))
pts = score.sample(v, f, score.SAMPLE_PER_M2)
c = pts.mean(axis=0)
th = np.radians(10)
rot = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
points = {
    "same": pts,
    "x20_scale": (pts - c) * 20 + c,
    "x0.05_scale": (pts - c) / 20 + c,
    "shift_3m": pts + [3, 0, 1],
    "rot10_scale1.2": ((pts - c) @ rot.T) * 1.2 + c,
    "copy_60m_east": np.r_[pts, pts + [60, 0, 0]],  # a second house beyond the outline
}
meshes = {"mesh_x0.05_scale": (v - c) / 20 + c, "mesh_x20_scale": (v - c) * 20 + c}  # as SAM 3D's MoGe mesh may be
results = {}
for name, p in points.items():
    np.save(R / f"scores/selftest-{name}.npy", p)
    results[name] = score.main(R, "b6", R / f"scores/selftest-{name}.npy")
for name, verts in meshes.items():
    np.savez(R / f"scores/selftest-{name}.npz", vertices=verts, faces=f)
    results[name] = score.main(R, "b6", R / f"scores/selftest-{name}.npz")
keys = ("roof_median_m", "roof_coverage", "footprint_iou", "scale", "fitted_scale", "shape_roof_median_m", "shape_roof_coverage")
for name, r in results.items():
    print(name, {k: r[k] for k in keys})

same = results["same"]
for name, r in results.items():
    if name == "copy_60m_east":
        continue  # two houses: not a distortion of one
    assert abs(r["shape_roof_median_m"] - same["shape_roof_median_m"]) < 0.03, (name, r["shape_roof_median_m"])
    assert r["shape_roof_coverage"] >= 0.95, (name, r["shape_roof_coverage"])
assert results["copy_60m_east"]["footprint_iou"] < 0.6 * same["footprint_iou"], results["copy_60m_east"]["footprint_iou"]
print("PASS")
