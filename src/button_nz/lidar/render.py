"""Turning grids into PNG images for a model to look at."""

import io
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

# A perceptually ordered scale from dark blue through green to yellow.
_STOPS = np.array(
    [
        [0.27, 0.0, 0.33],
        [0.23, 0.32, 0.55],
        [0.13, 0.57, 0.55],
        [0.37, 0.79, 0.38],
        [0.99, 0.91, 0.14],
    ]
)


@dataclass(frozen=True)
class View:
    """An image of measured data, the numbers behind it, and how to read it."""

    name: str
    png: bytes
    facts: Mapping[str, float]
    notes: str


def colour_scale(values: NDArray[np.float64], low: float, high: float) -> NDArray[np.uint8]:
    """RGB for ``values`` on a fixed scale from ``low`` to ``high`` (clamped), so
    the same colour always means the same value across views."""
    t = np.clip((values - low) / (high - low), 0.0, 1.0) * (len(_STOPS) - 1)
    lower = np.minimum(np.floor(t).astype(int), len(_STOPS) - 2)
    frac = (t - lower)[..., None]
    rgb = _STOPS[lower] * (1 - frac) + _STOPS[lower + 1] * frac
    return (rgb * 255).round().astype(np.uint8)


def to_png(rgb: NDArray[np.uint8], scale: int) -> bytes:
    """Encode ``rgb`` (rows x cols x 3), each cell drawn as ``scale`` x ``scale`` pixels."""
    pixels = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
    buffer = io.BytesIO()
    Image.fromarray(pixels, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def grey(values: NDArray[np.float64]) -> NDArray[np.uint8]:
    """RGB from 0-1 intensities."""
    level = (np.clip(values, 0.0, 1.0) * 255).round().astype(np.uint8)
    return np.repeat(level[..., None], 3, axis=2)
