"""Height maps, seen from above, of each model of one building against the
training-points DSM, on one colour scale, with the LINZ outline (#125).

usage: render_heights.py SPIKE_DIR BUILDING OUT_PNG
  (the SAM 3D env: it has matplotlib; score.py beside this does the rest)

Panels: the training-points DSM; Roofer; SAM 3D with the LiDAR pointmap, as
placed; the same after the scorer's alignment (condition 3); SAM 3D with MoGe
depth after the alignment (as placed it is ~20x too small, ~24 m off).
Each map is the highest model point per CELL_M cell (meshes sampled as score.py
samples them).
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from shapely.affinity import translate  # noqa: E402
from shapely.geometry import shape  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import score  # noqa: E402

CELL_M, MARGIN_M, RISE_M = 0.5, 6.0, 7.0


def mesh_points(path: Path, origin: tuple[float, float], outline, spike: Path, align: bool) -> np.ndarray:
    verts, faces = score.load_mesh(path, origin)
    pts = score.sample(verts, faces, score.SAMPLE_PER_M2 * score.size_ratio(outline, verts) ** 2)
    if not align:
        return pts
    s, rot, t = score.similarity_fit(score.top_points(pts), score.roof_surface(spike, outline, origin))
    return score.sample(s * verts @ rot.T + t, faces, score.SAMPLE_PER_M2)


def height_map(pts: np.ndarray, bounds: tuple[float, float, float, float]) -> np.ndarray:
    x0, y0, x1, y1 = bounds
    nx, ny = int((x1 - x0) / CELL_M), int((y1 - y0) / CELL_M)
    grid = np.full((ny, nx), np.nan)
    cx = ((pts[:, 0] - x0) / CELL_M).astype(int)
    cy = ((y1 - pts[:, 1]) / CELL_M).astype(int)
    ok = (cx >= 0) & (cx < nx) & (cy >= 0) & (cy < ny)
    order = np.argsort(pts[ok, 2])  # the last write per cell is the highest
    grid[cy[ok][order], cx[ok][order]] = pts[ok, 2][order]
    return grid


def main(spike: Path, building: str, out_png: Path) -> None:
    meta = json.loads((spike / f"train-{building}" / "outline.json").read_text())
    origin = tuple(meta["origin_nztm"])
    outline = translate(shape(meta["target"]), -origin[0], -origin[1])
    x0, y0, x1, y1 = outline.bounds
    bounds = (x0 - MARGIN_M, y0 - MARGIN_M, x1 + MARGIN_M, y1 + MARGIN_M)
    dsm = score.roof_surface(spike, outline.buffer(MARGIN_M * 1.5), origin)
    roofer = spike / "roofer" / "out" / "objects" / building / "reconstruct" / f"{building}.city.jsonl"
    sam = spike / f"train-{building}"
    panels = {
        "LiDAR, training points (1 m DSM)": dsm,
        "Roofer": mesh_points(roofer, origin, outline, spike, align=False),
        "SAM 3D + LiDAR pointmap, as placed": mesh_points(sam / "lidar" / "mesh.npz", origin, outline, spike, align=False),
        "SAM 3D + LiDAR pointmap, aligned": mesh_points(sam / "lidar" / "mesh.npz", origin, outline, spike, align=True),
        "SAM 3D + MoGe depth, aligned": mesh_points(sam / "moge" / "mesh.npz", origin, outline, spike, align=True),
    }
    ground = float(np.nanpercentile(dsm[:, 2], 2))
    fig, axes = plt.subplots(1, len(panels), figsize=(4 * len(panels), 4.4), constrained_layout=True)
    for ax, (title, pts) in zip(axes, panels.items()):
        grid = _dsm_grid(pts, bounds) if pts is dsm else height_map(pts, bounds)
        im = ax.imshow(grid - ground, extent=(bounds[0], bounds[2], bounds[1], bounds[3]), vmin=0, vmax=RISE_M, cmap="viridis")
        ox, oy = outline.exterior.xy
        ax.plot(ox, oy, color="red", lw=1.2)
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.colorbar(im, ax=axes, shrink=0.8, label="height above ground (m)")
    fig.suptitle(f"{building}: highest surface, seen from above; red line: LINZ outline", fontsize=10)
    fig.savefig(out_png, dpi=90)


def _dsm_grid(cells: np.ndarray, bounds: tuple[float, float, float, float]) -> np.ndarray:
    """The 1 m DSM cells (centres) as a grid at CELL_M, each cell filling its metre."""
    offsets = np.arange(-0.5 + CELL_M / 2, 0.5, CELL_M)
    dx, dy = np.meshgrid(offsets, offsets)
    filled = (cells[:, None, :] + np.c_[dx.ravel(), dy.ravel(), np.zeros(dx.size)][None]).reshape(-1, 3)
    return height_map(filled, bounds)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
