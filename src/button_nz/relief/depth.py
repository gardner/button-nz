"""Tier 0: the site's depth map, the LiDAR surface on the aerial's own pixels.

``png16`` is for a video editor's displacement (DaVinci Resolve's Fusion,
After Effects' Displacement Map): 0 is the lowest height on the site and
65535 the highest, ``low_m`` and ``high_m`` above the site's datum, linear
between. ``preview`` is the same at 8 bits, for people to look at. Higher is
brighter, as editors read a depth map that is a height map.
"""

import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from button_nz.relief import SiteRelief


@dataclass(frozen=True)
class DepthMap:
    png16: bytes
    preview: bytes
    low_m: float
    high_m: float


def depth_map(relief: SiteRelief) -> DepthMap:
    heights = relief.heights
    low, high = float(heights.min()), float(heights.max())
    if high <= low:
        raise ValueError("the site is flat: a depth map of it would say nothing")
    unit = (heights - low) / (high - low)
    return DepthMap(
        _png(np.round(unit * 65535).astype(np.uint16)),
        _png(np.round(unit * 255).astype(np.uint8)),
        low,
        high,
    )


def _png(values: NDArray[np.uint16] | NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(values).save(buffer, format="PNG")
    return buffer.getvalue()
