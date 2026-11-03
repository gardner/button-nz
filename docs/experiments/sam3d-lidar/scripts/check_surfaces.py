"""How far are split.py's training-points surfaces from LINZ's own 1 m rasters? (#125)

usage: check_surfaces.py SPLIT_DIR SITE_DIR
  SPLIT_DIR: split.py's output (train_dsm.tif, train_dem.tif)
  SITE_DIR:  the site's LINZ rasters (dsm.tif, dem.tif)

LINZ's raster is resampled (nearest) onto the training raster's grid, then the
absolute difference per cell is summarised (metres). LINZ's rasters are made
from every point, the held-out ones included.
"""

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject


def compare(ours_tif: Path, linz_tif: Path) -> dict[str, float | int]:
    with rasterio.open(ours_tif) as ours:
        z = ours.read(1)
        linz = np.full_like(z, np.nan)
        with rasterio.open(linz_tif) as src:
            reproject(rasterio.band(src, 1), linz, dst_transform=ours.transform, dst_crs=ours.crs,
                      src_nodata=src.nodata, dst_nodata=np.nan, resampling=Resampling.nearest)
    d = np.abs(z - linz)
    d = d[np.isfinite(d)]
    return {"cells": int(d.size), "median_m": round(float(np.median(d)), 3),
            "p90_m": round(float(np.percentile(d, 90)), 3), "p99_m": round(float(np.percentile(d, 99)), 3)}


def main(split: Path, site: Path) -> dict[str, dict[str, float | int]]:
    return {"dsm": compare(split / "train_dsm.tif", site / "dsm.tif"),
            "dem": compare(split / "train_dem.tif", site / "dem.tif")}


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), indent=1))
