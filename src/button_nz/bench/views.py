"""What the model sees under each Experiment A condition (plan §11): the aerial
photograph alone, with contours, with nDSM and slope maps, or with every fixed
map (``fixed_all``: hillshade, contours, nDSM, slope, normals); or the aerial plus the
observation tools it can call itself (``agent``). ``fixed_all`` against
``agent`` separates choosing views from merely having them.

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
from button_nz.lidar import View, contours, hillshade, ndsm_map, normal_map, slope_map

CONDITIONS = ("aerial", "aerial_contours", "aerial_ndsm_slope", "fixed_all", "agent")
SCALE = 8  # pixels per metre, as the agent's observation views
MARK_COLOUR = (255, 0, 255)
LABEL_PX = 12  # the label's height, with a gap
POINT_RADIUS_PX = 7  # a ring clear of the 1 m (8 px) cell it marks
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
    elif condition == "fixed_all":  # every map the agent could choose, given up front
        views = [
            hillshade(grid, scale=SCALE),
            contours(grid, CONTOUR_INTERVAL_M, SCALE),
            ndsm_map(grid, SCALE),
            slope_map(grid, SCALE),
            normal_map(grid, SCALE),
        ]
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
            # Outside the square, so every cell it asks about stays visible.
            above = py - h - LABEL_PX
            label_at = (px - h, above if above >= 0 else py + h + 3)
        else:
            r = POINT_RADIUS_PX
            draw.ellipse((px - r, py - r, px + r, py + r), outline=MARK_COLOUR, width=2)
            label_at = (px + r + 2, py - 2 * r)
        draw.text(label_at, target.label, fill=MARK_COLOUR)
    return _png(np.asarray(image, dtype=np.uint8))


def _png(rgb: NDArray[np.uint8]) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()
