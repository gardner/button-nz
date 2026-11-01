"""Split LINZ's LAZ points over a scene into held-out blocks and training points,
and make a DSM and DEM from the training points alone (#125, step 6).

usage: split.py LAZ SITE_JSON OUT_DIR

- Points in the scene's aerial box, noise (classes 7, 18) dropped.
- Held out: 20% of 2 m x 2 m blocks, chosen with a fixed seed, so a held-out
  point's neighbours are held out with it.
- train_dsm.tif: 1 m, highest training point in each cell; train_dem.tif: 1 m,
  lowest ground (class 2) training point. Empty cells (held-out blocks, gaps)
  are interpolated linearly from the training cells around them, never from
  held-out points. The grid matches LINZ's 1 m rasters (whole metres).
- Both rasters carry the compound CRS NZTM2000 + NZVD2016 height, so their
  values read as orthometric heights, not an unspecified Z.
"""

import json
import sys
from pathlib import Path

import laspy
import numpy as np
import rasterio
from rasterio.transform import from_origin
from scipy.interpolate import griddata

BLOCK_M, HELD_OUT, SEED = 2.0, 0.20, 125
NOISE = (7, 18)
CRS = "EPSG:2193+7839"  # NZTM2000 + NZVD2016 height, LINZ's own


def grid(x, y, z, bbox, reduce):
    west, south, east, north = bbox
    w, h = int(east - west), int(north - south)
    col = np.floor(x - west).astype(int)
    row = np.floor(north - y).astype(int)
    ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
    out = np.full(h * w, np.nan)
    idx = row[ok] * w + col[ok]
    vals = z[ok]
    order = np.argsort(vals)
    if reduce == "max":
        out[idx[order]] = vals[order]  # the last write per cell is the highest
    else:
        out[idx[order[::-1]]] = vals[order[::-1]]  # the last write is the lowest
    out = out.reshape(h, w)
    filled = np.isfinite(out)
    rr, cc = np.nonzero(filled)
    er, ec = np.nonzero(~filled)
    if len(er):
        out[er, ec] = griddata((rr, cc), out[rr, cc], (er, ec), method="linear")
        still = ~np.isfinite(out)
        if still.any():  # outside the hull of training cells: the nearest
            sr, sc = np.nonzero(still)
            out[sr, sc] = griddata((rr, cc), out[rr, cc], (sr, sc), method="nearest")
    return out.astype(np.float32), int((~filled).sum())


def write(path, data, bbox):
    west, _, _, north = bbox
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[1], height=data.shape[0],
                       count=1, dtype="float32", crs=CRS,
                       transform=from_origin(west, north, 1.0, 1.0), nodata=np.nan) as dst:
        dst.write(data, 1)


def main(laz: Path, site_json: Path, out: Path) -> None:
    bbox = [float(v) for v in json.loads(site_json.read_text())["aerial_bbox"]]
    west, south, east, north = bbox
    f = laspy.read(laz)
    x, y, z = np.asarray(f.x), np.asarray(f.y), np.asarray(f.z)
    cls = np.asarray(f.classification)
    keep = (x >= west) & (x < east) & (y >= south) & (y < north) & ~np.isin(cls, NOISE)
    x, y, z, cls = x[keep], y[keep], z[keep], cls[keep]
    bx = np.floor((x - west) / BLOCK_M).astype(int)
    by = np.floor((y - south) / BLOCK_M).astype(int)
    nbx, nby = int(np.ceil((east - west) / BLOCK_M)), int(np.ceil((north - south) / BLOCK_M))
    rng = np.random.default_rng(SEED)
    held_blocks = rng.random((nby, nbx)) < HELD_OUT
    held = held_blocks[by, bx]
    out.mkdir(parents=True, exist_ok=True)
    np.savez(out / "points.npz", train=np.c_[x[~held], y[~held], z[~held], cls[~held]],
             held_out=np.c_[x[held], y[held], z[held], cls[held]], bbox=np.array(bbox),
             block_m=BLOCK_M, held_out_share=HELD_OUT, seed=SEED, laz=str(laz.name))
    t = ~held
    dsm, dsm_filled = grid(x[t], y[t], z[t], bbox, "max")
    ground = t & (cls == 2)
    dem, dem_filled = grid(x[ground], y[ground], z[ground], bbox, "min")
    write(out / "train_dsm.tif", dsm, bbox)
    write(out / "train_dem.tif", dem, bbox)
    print(json.dumps({"points": int(keep.sum()), "train": int(t.sum()), "held_out": int(held.sum()),
                      "held_out_blocks": int(held_blocks.sum()), "blocks": int(held_blocks.size),
                      "dsm_cells_interpolated": dsm_filled, "dem_cells_interpolated": dem_filled,
                      "cells": int(dsm.size)}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
