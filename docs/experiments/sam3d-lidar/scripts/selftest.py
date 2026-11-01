"""The scorer on known distortions of Roofer's b6 model, as points (#125)."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))  # our own scorer, beside this
import score
R = Path(sys.argv[1]); meta = json.loads((R / "train-b6/outline.json").read_text())
v, f = score.cityjson_mesh(R / "roofer/out/objects/b6/reconstruct/b6.city.jsonl", tuple(meta["origin_nztm"]))
pts = score.sample(v, f, score.SAMPLE_PER_M2)
c = pts.mean(axis=0)
th = np.radians(10); rot = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
cases = {"same": pts, "x20_scale": (pts - c) * 20 + c, "shift_3m": pts + [3, 0, 1], "rot10_scale1.2": ((pts - c) @ rot.T) * 1.2 + c}
for name, p in cases.items():
    np.save(R / f"scores/selftest-{name}.npy", p)
    r = score.main(R, "b6", R / f"scores/selftest-{name}.npy")
    print(name, {k: r[k] for k in ("roof_median_m", "roof_coverage", "footprint_iou", "scale", "fitted_scale", "shape_roof_median_m", "shape_roof_coverage")})
