"""Cut one site's DSM, DEM, aerial and one LINZ outline into a local-frame scene.npz for Blender.

usage: prep.py SITE_DIR BUILDING_INDEX OUT_DIR [DSM DEM]
DSM, DEM: the surfaces to use instead of the site's LINZ rasters, e.g. split.py's
train_dsm.tif and train_dem.tif made from the training points only (#125 step 6).
Local frame: metres from the target outline's centroid, +x east, +y north, z = NZVD2016 height.
"""

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.transform import from_origin
from shapely.geometry import mapping, shape

GRID_M = 0.25  # mesh spacing; the DSM itself is 1 m


def resample(path: Path, bbox: list[float], cell: float) -> np.ndarray:
    west, south, east, north = bbox
    width, height = round((east - west) / cell), round((north - south) / cell)
    out = np.full((height, width), np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        reproject(
            rasterio.band(src, 1),
            out,
            dst_transform=from_origin(west, north, cell, cell),
            dst_crs=src.crs,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    if np.isnan(out).any():
        raise ValueError(f"{path} has holes over the aerial bbox")
    return out


def main(site_dir: Path, index: int, out_dir: Path, dsm_tif: Path, dem_tif: Path) -> None:
    site = json.loads((site_dir / "site.json").read_text())
    bbox = [float(v) for v in site["aerial_bbox"]]
    outlines = json.loads((site_dir / "buildings.geojson").read_text())["features"]
    outline = shape(outlines[index]["geometry"])
    cx, cy = outline.centroid.coords[0]
    dsm = resample(dsm_tif, bbox, GRID_M)
    dem = resample(dem_tif, bbox, GRID_M)
    others = [shape(f["geometry"]) for i, f in enumerate(outlines) if i != index]
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        out_dir / "scene.npz",
        dsm=dsm,
        dem=dem,
        cell=GRID_M,
        bbox_local=np.array([bbox[0] - cx, bbox[1] - cy, bbox[2] - cx, bbox[3] - cy]),
        origin_nztm=np.array([cx, cy]),
        surfaces=np.array([str(dsm_tif), str(dem_tif)]),
    )
    (out_dir / "outline.json").write_text(
        json.dumps(
            {
                "target": mapping(outline),
                "others": [mapping(o) for o in others],
                "origin_nztm": [cx, cy],
                "area_m2": outline.area,
            }
        )
    )
    print(f"scene {dsm.shape} centroid {cx:.1f},{cy:.1f} area {outline.area:.0f} m2")


if __name__ == "__main__":
    site = Path(sys.argv[1])
    surfaces = (Path(sys.argv[4]), Path(sys.argv[5])) if len(sys.argv) > 5 else (site / "dsm.tif", site / "dem.tif")
    main(site, int(sys.argv[2]), Path(sys.argv[3]), *surfaces)
