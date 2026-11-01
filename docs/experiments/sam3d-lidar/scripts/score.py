"""Score a building model against the held-out LiDAR points (#125, step 5).

usage: score.py SPIKE_DIR BUILDING MODEL
  BUILDING: b6 or b3 (SPIKE_DIR/train-BUILDING/outline.json gives the local frame)
  MODEL:    a Roofer CityJSONSeq (.city.jsonl, NZTM) or SAM 3D's scene_points.npy
            (Gaussian centres, local site frame)

Every model is reduced to the same thing, points on its surface (a mesh is
sampled at SAMPLE_PER_M2), in the local frame: metres east and north of the
outline's centroid, z = NZVD2016 height. Then:

Metric layout, no alignment:
- roof_rmse_m, roof_median_m: for each held-out building point inside the
  outline, its vertical distance to the model's top surface there (the
  highest model point within TOP_RADIUS_M horizontally); points with no model
  above them count as misses (roof_coverage). roof_bias_m: the signed median
  (positive: the model sits above the points).
- height_err_m: the model's roof height above ground (98th percentile) less
  the held-out points' (ground: the training-points DEM, median under the
  outline).
- footprint_iou: the model's footprint (cells of FOOT_CELL_M holding a model
  point) against the LINZ outline. Adherence to the mask: the mask came from
  the outline.
- scale: the model footprint's principal lengths over the outline's (both as
  FOOT_CELL_M cells, 2nd to 98th percentile).

Shape, after the best similarity alignment (scale, rotation, translation)
of the model's top surface (its highest point per FOOT_CELL_M cell) to the
training-points DSM inside the outline (a whole roof, from training points only):
- shape_roof_rmse_m, shape_roof_median_m, shape_roof_bias_m: as above, after
  alignment.
- fitted_scale: the scale the alignment needed.

Meshes only:
- roof_exact_median_m, roof_exact_bias_m: the mesh's own top surface straight
  above each held-out roof point, with no radius. The highest point within
  TOP_RADIUS_M leans upward on a pitched roof (it is the upslope point), so
  this shows how much of roof_median_m is the measure, not the model.
- validity: watertight (every edge shared by exactly two faces).
"""

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.affinity import translate
from shapely.geometry import Polygon, shape

SAMPLE_PER_M2 = 25.0
TOP_RADIUS_M = 0.5
FOOT_CELL_M = 0.5
BUILDING = 6

Array = NDArray[np.float64]


# ---------- models -> surface points (local frame)


def cityjson_mesh(path: Path, origin: tuple[float, float]) -> tuple[Array, NDArray[np.int64]]:
    """A Roofer CityJSONSeq building's LoD 2.2 solid as triangles, local frame."""
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    meta = next((line for line in lines if line.get("type") == "CityJSON"), None)
    if meta is None:  # split output: the transform is in the run's metadata.json
        run = next(p for p in path.parents if (p / "metadata.json").is_file())
        meta = json.loads((run / "metadata.json").read_text())
    feature = next(line for line in lines if line.get("type") == "CityJSONFeature")
    scale, shift = np.array(meta["transform"]["scale"]), np.array(meta["transform"]["translate"])
    verts = np.array(feature["vertices"], float) * scale + shift
    verts[:, 0] -= origin[0]
    verts[:, 1] -= origin[1]
    faces: list[list[int]] = []
    for obj in feature["CityObjects"].values():
        for geom in obj.get("geometry", []):
            if str(geom.get("lod")) != "2.2":
                continue
            shells = geom["boundaries"] if geom["type"] == "Solid" else [geom["boundaries"]]
            for shell in shells:
                for surface in shell:
                    faces += _triangulate(verts, surface)
    return verts, np.array(faces, dtype=np.int64)


def _triangulate(verts: Array, surface: list[list[int]]) -> list[list[int]]:
    """A planar polygon (outer ring, holes) as triangles of its own vertices."""
    from shapely import constrained_delaunay_triangles

    outer = surface[0]
    pts = verts[outer]
    normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    for i in range(2, len(pts)):  # the first non-degenerate normal
        if np.linalg.norm(normal) > 1e-9:
            break
        normal = np.cross(pts[1] - pts[0], pts[i] - pts[0])
    normal /= np.linalg.norm(normal)
    u = np.cross(normal, [0, 0, 1.0]) if abs(normal[2]) < 0.9 else np.cross(normal, [1.0, 0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    rings = [[(float(verts[i] @ u), float(verts[i] @ v)) for i in ring] for ring in surface]
    index = {xy: i for ring, ids in zip(rings, surface) for xy, i in zip(ring, ids)}
    tris = constrained_delaunay_triangles(Polygon(rings[0], rings[1:]))
    out: list[list[int]] = []
    for tri in tris.geoms:
        corners = [index.get((float(x), float(y))) for x, y in list(tri.exterior.coords)[:3]]
        if None not in corners:
            out.append([c for c in corners if c is not None])
    return out


def sample(verts: Array, faces: NDArray[np.int64], per_m2: float, seed: int = 0) -> Array:
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    rng = np.random.default_rng(seed)
    n = rng.poisson(area * per_m2)
    which = np.repeat(np.arange(len(faces)), n)
    r1, r2 = rng.random(len(which)), rng.random(len(which))
    s = np.sqrt(r1)
    return (1 - s)[:, None] * a[which] + (s * (1 - r2))[:, None] * b[which] + (s * r2)[:, None] * c[which]


def validity(verts: Array, faces: NDArray[np.int64]) -> dict[str, Any]:
    edges: dict[tuple[int, int], int] = {}
    for f in faces:
        for i in range(3):
            e = (int(min(f[i], f[(i + 1) % 3])), int(max(f[i], f[(i + 1) % 3])))
            edges[e] = edges.get(e, 0) + 1
    watertight = all(n == 2 for n in edges.values())
    return {"watertight": watertight, "triangles": len(faces)}  # every edge on two faces


# ---------- measures


def top_errors(model: Array, truth: Array) -> tuple[Array, float]:
    """Vertical error of the model's top surface at each truth point; coverage."""
    tree = cKDTree(model[:, :2])
    near = tree.query_ball_point(truth[:, :2], TOP_RADIUS_M)
    err = np.full(len(truth), np.nan)
    for i, idx in enumerate(near):
        if idx:
            err[i] = model[idx, 2].max() - truth[i, 2]
    covered = np.isfinite(err)
    return err[covered], float(covered.mean())


def mesh_top_errors(verts: Array, faces: NDArray[np.int64], truth: Array) -> tuple[Array, float]:
    """Vertical error of a mesh's top surface straight above each truth point
    (the highest triangle there); coverage. Walls, edge-on from above, are skipped."""
    top = np.full(len(truth), np.nan)
    px, py = truth[:, 0], truth[:, 1]
    for (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) in verts[faces]:
        det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(det) < 1e-9:
            continue
        l1 = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / det
        l2 = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / det
        l3 = 1 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        top = np.where(inside, np.fmax(top, l1 * z1 + l2 * z2 + l3 * z3), top)
    err = top - truth[:, 2]
    covered = np.isfinite(err)
    return err[covered], float(covered.mean())


def footprint_iou(model: Array, outline: Polygon) -> float:
    x0, y0, x1, y1 = outline.buffer(30).bounds
    nx, ny = int((x1 - x0) / FOOT_CELL_M), int((y1 - y0) / FOOT_CELL_M)
    occ = np.zeros((ny, nx), bool)
    cx = ((model[:, 0] - x0) / FOOT_CELL_M).astype(int)
    cy = ((model[:, 1] - y0) / FOOT_CELL_M).astype(int)
    ok = (cx >= 0) & (cx < nx) & (cy >= 0) & (cy < ny)
    occ[cy[ok], cx[ok]] = True
    gx, gy = np.meshgrid(x0 + (np.arange(nx) + 0.5) * FOOT_CELL_M, y0 + (np.arange(ny) + 0.5) * FOOT_CELL_M)
    inside = contains_xy(outline, gx, gy)
    return float((occ & inside).sum() / max((occ | inside).sum(), 1))


def outline_cells(outline: Polygon) -> Array:
    """The centres of the FOOT_CELL_M cells inside the outline: its area as points."""
    x0, y0, x1, y1 = outline.bounds
    gx, gy = np.meshgrid(np.arange(x0, x1, FOOT_CELL_M) + FOOT_CELL_M / 2, np.arange(y0, y1, FOOT_CELL_M) + FOOT_CELL_M / 2)
    inside = contains_xy(outline, gx, gy)
    return np.c_[gx[inside], gy[inside]]


def footprint_cells(model: Array) -> Array:
    """The centres of the FOOT_CELL_M cells holding a model point: its footprint as points."""
    cells = np.unique(np.floor(model[:, :2] / FOOT_CELL_M).astype(np.int64), axis=0)
    return (cells + 0.5) * FOOT_CELL_M


def principal_lengths(xy: Array) -> Array:
    centred = xy - xy.mean(axis=0)
    _, vecs = np.linalg.eigh(np.cov(centred.T))
    proj = centred @ vecs
    return np.sort(np.percentile(proj, 98, axis=0) - np.percentile(proj, 2, axis=0))


def roof_surface(spike: Path, outline: Polygon, origin: tuple[float, float]) -> Array:
    """The training-points DSM inside the outline, one point per 1 m cell: a
    whole roof to align to, holes interpolated from training points only."""
    import rasterio

    with rasterio.open(spike / "split" / "train_dsm.tif") as src:
        z = src.read(1)
        west, north = src.transform.c, src.transform.f
    rows, cols = np.indices(z.shape)
    x = west + cols + 0.5 - origin[0]
    y = north - rows - 0.5 - origin[1]
    inside = contains_xy(outline, x, y)
    return np.c_[x[inside], y[inside], z[inside]].astype(float)


TOP_CELLS_ACROSS = 40  # the top surface's cells across the model, whatever its scale


def top_points(model: Array) -> Array:
    """The model's highest point in each cell: its roof, seen from above. The
    cell is a fortieth of the model's width, whatever its scale (about 0.5 m
    for a house at true size), so a model 20x too big or too small still gives
    the same number of top points, each roof, not a floor or wall point alone
    in a cell."""
    width = float(np.max(np.percentile(model[:, :2], 98, axis=0) - np.percentile(model[:, :2], 2, axis=0)))
    cell = width / TOP_CELLS_ACROSS
    cells = np.floor(model[:, :2] / cell).astype(np.int64)
    order = np.lexsort((-model[:, 2], cells[:, 1], cells[:, 0]))
    c = cells[order]
    first = np.r_[True, (c[1:] != c[:-1]).any(axis=1)]
    return model[order][first]


def similarity_fit(src: Array, dst: Array, rounds: int = 60, keep: float = 0.95) -> tuple[float, Array, Array]:
    """Scale, rotation and translation taking src onto dst: ICP with scale
    (Umeyama each round), started from the two clouds' centroids and spreads
    (so a model 20x too big still converges), pairing each point both ways
    (src to its nearest dst, and dst to its nearest src, so neither excess
    model nor uncovered truth goes unpenalised), the two directions weighted
    equally however many points each has, and dropping each direction's worst
    (1 - keep) of pairs."""
    s = float(np.sqrt(np.var(dst, axis=0).sum() / np.var(src, axis=0).sum()))
    rot, t = np.eye(3), dst.mean(axis=0) - s * src.mean(axis=0)
    dst_tree = cKDTree(dst)
    for _ in range(rounds):
        moved = s * src @ rot.T + t
        d1, j1 = dst_tree.query(moved)  # each model point to the truth
        d2, j2 = cKDTree(moved).query(dst)  # each truth point to the model
        a = np.r_[src, src[j2]]
        b = np.r_[dst[j1], dst]
        d = np.r_[d1, d2]
        w = np.r_[np.full(len(src), 0.5 / len(src)), np.full(len(dst), 0.5 / len(dst))]
        kept = np.r_[d1 <= np.quantile(d1, keep), d2 <= np.quantile(d2, keep)]
        s, rot, t = _umeyama(a[kept], b[kept], w[kept])
    return s, rot, t


def _umeyama(src: Array, dst: Array, w: Array) -> tuple[float, Array, Array]:
    """Weighted least-squares similarity src -> dst (Umeyama 1991)."""
    w = w / w.sum()
    mu_s, mu_d = w @ src, w @ dst
    a, b = src - mu_s, dst - mu_d
    u, d, vt = np.linalg.svd((b * w[:, None]).T @ a)
    sign = np.diag([1.0, 1.0, np.sign(np.linalg.det(u @ vt))])
    rot = u @ sign @ vt
    s = float(np.trace(np.diag(d) @ sign) / (w @ (a**2).sum(axis=1)))
    return s, rot, mu_d - s * rot @ mu_s


def stats(err: Array) -> tuple[float, float]:
    return float(np.sqrt(np.mean(err**2))), float(np.median(np.abs(err)))


def main(spike: Path, building: str, model_path: Path) -> dict[str, Any]:
    meta = json.loads((spike / f"train-{building}" / "outline.json").read_text())
    ox, oy = meta["origin_nztm"]
    outline = translate(shape(meta["target"]), -ox, -oy)
    pts = np.load(spike / "split" / "points.npz")
    held = pts["held_out"] - [ox, oy, 0, 0]  # local frame; column 3 is the class
    held_roof = held[(held[:, 3] == BUILDING) & contains_xy(outline, held[:, 0], held[:, 1])][:, :3]
    result: dict[str, Any] = {"building": building, "model": str(model_path), "held_out_roof_points": len(held_roof)}
    if model_path.suffix == ".npy":
        model = np.load(model_path).astype(float)
    else:
        verts, faces = cityjson_mesh(model_path, (ox, oy))
        model = sample(verts, faces, SAMPLE_PER_M2)
        result["validity"] = validity(verts, faces)
        exact, _ = mesh_top_errors(verts, faces, held_roof)
        result |= {"roof_exact_median_m": round(float(np.median(np.abs(exact))), 3), "roof_exact_bias_m": round(float(np.median(exact)), 3)}
    result["model_points"] = len(model)

    import rasterio

    with rasterio.open(spike / "split" / "train_dem.tif") as dem:
        gx, gy = outline.centroid.x + ox, outline.centroid.y + oy
        ground = float(np.median([v[0] for v in dem.sample([(gx + dx, gy + dy) for dx in (-3, 0, 3) for dy in (-3, 0, 3)])]))
    err, cover = top_errors(model, held_roof)
    rmse, med = stats(err)
    result |= {
        "roof_rmse_m": round(rmse, 3),
        "roof_median_m": round(med, 3),
        "roof_bias_m": round(float(np.median(err)), 3),
        "roof_coverage": round(cover, 3),
        "height_err_m": round(float(np.percentile(model[:, 2], 98) - np.percentile(held_roof[:, 2], 98)), 3),
        "ground_m": round(ground, 2),
        "footprint_iou": round(footprint_iou(model, outline), 3),
        "scale": [round(float(v), 3) for v in principal_lengths(footprint_cells(model)) / principal_lengths(outline_cells(outline))],
    }
    s, rot, t = similarity_fit(top_points(model), roof_surface(spike, outline, (ox, oy)))
    aligned = s * model @ rot.T + t
    err2, cover2 = top_errors(aligned, held_roof)
    rmse2, med2 = stats(err2)
    result |= {"fitted_scale": round(s, 3), "shape_roof_rmse_m": round(rmse2, 3), "shape_roof_median_m": round(med2, 3),
               "shape_roof_bias_m": round(float(np.median(err2)), 3), "shape_roof_coverage": round(cover2, 3)}
    return result


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])), indent=1))
