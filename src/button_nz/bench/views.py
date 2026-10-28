"""What the model sees under each Experiment A condition (plan §11): the aerial
photograph alone, with contours, or with nDSM and slope maps; or the aerial
plus the observation tools it can call itself (``agent``).

Every image covers the LiDAR grid's bbox at ``SCALE`` pixels per metre, north
up, with the question's marks drawn on it, so an image's pixels line up with
the coordinates in the question.
"""

import io

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from button_nz.agent.site import DesignSite
from button_nz.bench.questions import Mark, Question
from button_nz.lidar import View, contours, ndsm_map, slope_map

CONDITIONS = ("aerial", "aerial_contours", "aerial_ndsm_slope", "agent")
SCALE = 8  # pixels per metre, as the agent's observation views
MARK_COLOUR = (255, 0, 255)
POINT_RADIUS_PX = 5
CONTOUR_INTERVAL_M = 0.25


def condition_images(
    condition: str, question: Question, site: DesignSite, aerial: NDArray[np.uint8]
) -> list[tuple[str, bytes]]:
    """Captioned PNGs for ``condition``: the aerial first, then any LiDAR views."""
    grid = site.context.terrain
    rows, cols = grid.dem.shape
    expected = (round(rows * grid.cell_m * SCALE), round(cols * grid.cell_m * SCALE), 3)
    if aerial.shape != expected:
        raise ValueError(f"the aerial is {aerial.shape}, not {expected} (the grid at {SCALE}/m)")
    images = [("Aerial photograph.", _png(aerial))]
    views: list[View] = []
    if condition == "aerial_contours":
        views = [contours(grid, CONTOUR_INTERVAL_M, SCALE)]
    elif condition == "aerial_ndsm_slope":
        views = [ndsm_map(grid, SCALE), slope_map(grid, SCALE)]
    elif condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    images += [(view.notes, view.png) for view in views]  # each says how to read it
    note = f" North up, {SCALE} px per metre, marks in magenta."
    return [(caption + note, mark(png, question.marks, site)) for caption, png in images]


def mark(png: bytes, marks: tuple[Mark, ...], site: DesignSite) -> bytes:
    """``png`` (a view of the LiDAR grid at ``SCALE``) with ``marks`` drawn on it."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    west, _, _, north = site.context.terrain.bbox
    for target in marks:
        x, y = site.frame.to_nztm((target.x, target.y))
        px, py = (x - west) * SCALE, (north - y) * SCALE
        if target.half_m:
            h = target.half_m * SCALE
            draw.rectangle((px - h, py - h, px + h, py + h), outline=MARK_COLOUR, width=2)
            label_at = (px - h + 3, py - h + 2)
        else:
            r = POINT_RADIUS_PX
            draw.ellipse((px - r, py - r, px + r, py + r), fill=MARK_COLOUR)
            label_at = (px + r + 2, py - 2 * r)
        draw.text(label_at, target.label, fill=MARK_COLOUR)
    return _png(np.asarray(image, dtype=np.uint8))


def _png(rgb: NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()
