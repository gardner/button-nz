"""The results table, built from the score files (#125).

usage: summarize.py SCORES_DIR > summary.md
  SCORES_DIR: score.py's outputs: sam3d-{moge,lidar}-{b6,b3}.json (seed 42),
  seeds/sam3d-{moge,lidar}-{b6,b3}-s{1..5}.json and roofer-{b6,b3}.json.

Each SAM 3D row is the median over the six seeds, with the range in brackets;
"closed solids" counts the meshes with every edge on two faces.
"""

import json
import sys
from pathlib import Path

import numpy as np

COLUMNS = ("footprint_iou", "roof_median_m", "roof_exact_median_m", "height_err_m", "fitted_scale", "shape_roof_median_m", "shape_roof_coverage")
BUILDINGS = {"b6": "house", "b3": "behind trees"}
CONDITIONS = {"moge": "SAM 3D, MoGe depth", "lidar": "SAM 3D, LiDAR pointmap"}


def cell(values: list[float | None]) -> str:
    known = [v for v in values if v is not None]
    if not known:
        return "—"  # no held-out point under any of the models
    if len(values) == 1:
        return f"{known[0]:.2f}"
    lo, mid, hi = min(known), float(np.median(known)), max(known)
    missing = f", {len(values) - len(known)} none" if len(known) < len(values) else ""
    return f"{mid:.2f} ({lo:.2f} to {hi:.2f}{missing})"


def row(name: str, runs: list[dict]) -> str:
    closed = sum(r["validity"]["watertight"] for r in runs)
    cells = [cell([r[c] for r in runs]) for c in COLUMNS]
    return f"| {name} | " + " | ".join(cells) + f" | {closed}/{len(runs)} |"


def main(scores: Path) -> str:
    lines = ["| Building, model | " + " | ".join(COLUMNS) + " | closed solids |", "|---" * (len(COLUMNS) + 2) + "|"]
    for b, label in BUILDINGS.items():
        for c, model in CONDITIONS.items():
            runs = [json.loads((scores / f"sam3d-{c}-{b}.json").read_text())]
            runs += [json.loads(p.read_text()) for p in sorted((scores / "seeds").glob(f"sam3d-{c}-{b}-s*.json"))]
            lines.append(row(f"{b} ({label}), {model} ({len(runs)} seeds)", runs))
        lines.append(row(f"{b} ({label}), Roofer", [json.loads((scores / f"roofer-{b}.json").read_text())]))
    return "\n".join(lines)


if __name__ == "__main__":
    print(main(Path(sys.argv[1])))
