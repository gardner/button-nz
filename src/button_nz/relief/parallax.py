"""Tier 1: the photo lifted onto its heights and seen at a tilt, in plain numpy.

An oblique parallel projection: the camera looks towards ``bearing_deg``
(compass), tilted ``tilt_deg`` from straight down. The photo is first turned
so the camera looks up the frame. A point ``y`` metres down the turned photo
and ``h`` metres up lands ``y cos(tilt) - h sin(tilt)`` down the screen, so
height lifts it towards the top.

Each column is drawn near to far. A sample shows from its own screen row
down to the highest row anything nearer has reached (the running minimum),
so tall things hide what's behind them and nothing is left as a hole. Below
a roof edge, that stretches the edge's colour down as its wall. Ground that
faces the camera is shaded by how steeply it does: a wall by ``WALL_SHADE``,
flat ground not at all, fading in as the camera tilts. The shade is the
slope's, never a pixel's, so a slope shades smoothly instead of in bands.
"""

import math

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from button_nz.relief.camera import ease

BACKGROUND = (226, 232, 238)  # beyond the photo: a pale sky
WALL_SHADE = 0.75
FULL_SHADE_TILT_DEG = 30.0  # straight down a wall can't be seen: its shade fades in to here

type Pose = tuple[float, float]  # tilt from straight down, compass bearing


def oblique(
    photo: NDArray[np.uint8],
    heights: NDArray[np.float64],
    pixel_m: float,
    tilt_deg: float,
    bearing_deg: float,
    centre_m: float,
) -> NDArray[np.uint8]:
    """``photo`` (north up) over ``heights`` (metres, on its pixels), the same
    size, with the middle of the photo at ``centre_m`` up at the frame's centre."""
    if heights.shape != photo.shape[:2]:
        raise ValueError(f"heights are {heights.shape}, not the photo's {photo.shape[:2]}")
    colours, lifted, valid = _turned(photo, heights, bearing_deg)
    tilt = math.radians(tilt_deg)
    rows = photo.shape[0]
    down = np.arange(rows, dtype=np.float64)[:, None] + 0.5 - rows / 2
    lift = (lifted - centre_m) / pixel_m
    screen = np.where(valid, down * math.cos(tilt) - lift * math.sin(tilt) + rows / 2, np.inf)
    seen = min(1.0, tilt_deg / FULL_SHADE_TILT_DEG)
    shaded = _shaded(colours, lifted, valid, pixel_m, seen)
    # Near to far: the camera is beyond the bottom of the turned photo.
    near, shaded = screen[::-1], shaded[::-1]
    sample = _drawn_by(np.minimum.accumulate(near, axis=0))
    return _paint(shaded, near, sample)


def sway_path(frames: int, tilt_deg: float, sway_deg: float, bearing_deg: float) -> list[Pose]:
    """A loop: rise from straight down to ``tilt_deg`` (the first quarter),
    sway ``sway_deg`` either side of ``bearing_deg`` (the middle half), then
    settle back down (the last quarter), stopping a frame short of the first
    so it doesn't show twice as the clip loops."""
    path: list[Pose] = []
    for frame in range(frames):
        t = frame / frames
        if t < 0.25:
            path.append((tilt_deg * ease(t / 0.25), bearing_deg))
        elif t <= 0.75:
            turn = math.sin(2 * math.pi * (t - 0.25) / 0.5)
            path.append((tilt_deg, bearing_deg + sway_deg * turn))
        else:
            path.append((tilt_deg * ease((1 - t) / 0.25), bearing_deg))
    return path


def _turned(
    photo: NDArray[np.uint8], heights: NDArray[np.float64], bearing_deg: float
) -> tuple[NDArray[np.uint8], NDArray[np.float64], NDArray[np.bool_]]:
    """The photo, its heights and where it has any, turned anticlockwise by
    the bearing so the camera's view points up the frame."""
    if bearing_deg % 360 == 0:
        return photo, heights, np.ones(heights.shape, dtype=bool)
    bilinear, nearest = Image.Resampling.BILINEAR, Image.Resampling.NEAREST
    rgb = Image.fromarray(photo).rotate(bearing_deg, bilinear)
    lifted = Image.fromarray(heights.astype(np.float32), "F").rotate(bearing_deg, bilinear)
    inside = Image.fromarray(np.full(heights.shape, 255, np.uint8)).rotate(bearing_deg, nearest)
    return (
        np.asarray(rgb, dtype=np.uint8),
        np.asarray(lifted, dtype=np.float64),
        np.asarray(inside) > 0,
    )


def _shaded(
    colours: NDArray[np.uint8],
    lifted: NDArray[np.float64],
    valid: NDArray[np.bool_],
    pixel_m: float,
    seen: float,
) -> NDArray[np.uint8]:
    """Each sample darkened by how steeply its ground faces the camera (rises
    from the sample nearer it): the sine of that slope, up to ``WALL_SHADE``
    when ``seen`` is 1."""
    rise = np.zeros_like(lifted)
    rise[:-1] = np.where(valid[1:], lifted[:-1] - lifted[1:], 0.0)  # row + 1 is nearer
    steep = np.clip(rise, 0.0, None) / pixel_m
    shade = 1 - (1 - WALL_SHADE) * seen * steep / np.sqrt(1 + steep**2)
    return np.round(colours * shade[..., None]).astype(np.uint8)


def _drawn_by(horizon: NDArray[np.float64]) -> NDArray[np.intp]:
    """For each screen pixel (row, column), the first sample, near to far,
    whose running minimum reaches the pixel's centre; ``len(horizon)`` if none
    does (the sky beyond the photo)."""
    centres = np.arange(horizon.shape[0], dtype=np.float64) + 0.5
    # The running minimum only falls, so its negation only rises: searchable.
    columns = [np.searchsorted(-column, -centres) for column in horizon.T]
    return np.stack(columns, axis=1)


def _paint(
    colours: NDArray[np.uint8], near: NDArray[np.float64], sample: NDArray[np.intp]
) -> NDArray[np.uint8]:
    rows, cols = sample.shape
    column: NDArray[np.intp] = np.broadcast_to(np.arange(cols, dtype=np.intp), (rows, cols))
    found = np.minimum(sample, rows - 1)
    centres = np.arange(rows, dtype=np.float64)[:, None] + 0.5
    below: NDArray[np.float64] = centres - near[found, column]
    # The nearest sample a column has reaches only half a row past its centre.
    first = np.argmax(np.isfinite(near), axis=0)[None, :]
    sky: NDArray[np.bool_] = (sample == rows) | ((sample == first) & (below > 0.5))
    view = colours[found, column].copy()
    view[sky] = BACKGROUND
    return view
