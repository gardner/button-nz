"""Aerial photographs of a site: an RGB crop of NZTM image tiles, resampled to
a chosen pixel size so it lines up with the LiDAR views of the same bbox.

A bbox may span several tiles; each pixel comes from the first tile with a
valid pixel there (nodata, alpha and mask holes don't count). Every pixel must
be covered: nothing is padded or invented at the edges.
"""

from collections.abc import Sequence
from typing import Any, cast

import numpy as np
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

from button_nz.geo.geometry import BBox

NZTM = 2193

# rasterio has no type stubs (see terrain.py): typed Any, converted at once.
rio: Any = rasterio


def read_aerial(assets: Sequence[str], bbox: BBox, pixel_m: float) -> NDArray[np.uint8]:
    """``bbox`` of the images at ``assets`` as rows x columns x RGB, north row
    first, one pixel per ``pixel_m`` metres (bilinear within each tile)."""
    west, south, east, north = bbox
    rows, cols = round((north - south) / pixel_m), round((east - west) / pixel_m)
    out = np.zeros((rows, cols, 3), dtype=np.uint8)
    covered = np.zeros((rows, cols), dtype=bool)
    for asset in assets:
        with rio.open(asset) as image:
            part = _overlap(image, asset, bbox)
            if part is None:
                continue
            r0, r1 = round((north - part[3]) / pixel_m), round((north - part[1]) / pixel_m)
            c0, c1 = round((part[0] - west) / pixel_m), round((part[2] - west) / pixel_m)
            if r1 <= r0 or c1 <= c0:
                continue
            window = rio.windows.from_bounds(*part, transform=image.transform)
            data = cast(
                "NDArray[np.uint8]",
                image.read(
                    (1, 2, 3),
                    window=window,
                    out_shape=(3, r1 - r0, c1 - c0),
                    resampling=rio.enums.Resampling.bilinear,
                ),
            )
            # Only the tile's valid pixels (not nodata, alpha or mask holes) cover.
            mask = image.dataset_mask(
                window=window,
                out_shape=(r1 - r0, c1 - c0),
                resampling=rio.enums.Resampling.nearest,
            )
        fill = (np.asarray(mask) > 0) & ~covered[r0:r1, c0:c1]
        out[r0:r1, c0:c1][fill] = np.moveaxis(data, 0, -1)[fill]
        covered[r0:r1, c0:c1] |= fill
    if not covered.all():
        raise ValueError(f"{bbox} is not covered by {list(assets)}")
    return out


def _overlap(image: Any, asset: str, bbox: BBox) -> BBox | None:
    """The part of ``bbox`` inside ``image``, after checking it's NZTM RGB."""
    if image.crs is None or image.crs.to_epsg() != NZTM:
        raise ValueError(f"{asset} is not in EPSG:2193 (NZTM)")
    if image.count < 3:
        raise ValueError(f"{asset} has {image.count} band(s), not RGB")
    left, bottom, right, top = (float(v) for v in image.bounds)
    part = (max(bbox[0], left), max(bbox[1], bottom), min(bbox[2], right), min(bbox[3], top))
    return part if part[0] < part[2] and part[1] < part[3] else None
