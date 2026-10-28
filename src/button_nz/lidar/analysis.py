"""Measurements from the terrain grid: slope, normals, cross-sections and
elevation statistics. Coordinates are NZTM metres; heights NZVD2016."""

import io
import math
from dataclasses import dataclass
from typing import cast

import numpy as np
import shapely
from numpy.typing import NDArray
from PIL import Image, ImageDraw
from shapely import Polygon

from button_nz.geo.geometry import Point, Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.lidar.render import View


def gradients(grid: TerrainGrid) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """dz/dx (east) and dz/dy (north) at each cell, in m per m."""
    d_row, d_col = cast("list[NDArray[np.float64]]", np.gradient(grid.dem, grid.cell_m))
    return d_col, -d_row  # row 0 is the north edge, so rows grow southward


def slope_degrees(grid: TerrainGrid) -> NDArray[np.float64]:
    east, north = gradients(grid)
    return np.degrees(np.arctan(np.hypot(east, north)))


def normals(grid: TerrainGrid) -> NDArray[np.float64]:
    """Unit surface normals (x east, y north, z up), shape rows x cols x 3."""
    east, north = gradients(grid)
    n = np.stack([-east, -north, np.ones_like(east)], axis=-1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


@dataclass(frozen=True)
class CrossSection:
    distances: list[float]  # metres from the start
    heights: list[float]  # NZVD2016 metres
    view: View


def cross_section(grid: TerrainGrid, start: Point, end: Point, step_m: float = 0.5) -> CrossSection:
    """The terrain along the line ``start``-``end``, sampled every ``step_m``
    (bilinear between cell centres, as the terrain mesh interpolates)."""
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    n = max(1, math.ceil(length / step_m))
    distances = [length * i / n for i in range(n + 1)]
    points = [
        (start[0] + (end[0] - start[0]) * d / length, start[1] + (end[1] - start[1]) * d / length)
        if length
        else start
        for d in distances
    ]
    heights = [_height_at(grid, p) for p in points]
    facts = {
        "length_m": length,
        "min_m": min(heights),
        "max_m": max(heights),
        "relief_m": max(heights) - min(heights),
    }
    notes = (
        f"Terrain profile from ({start[0]:.1f}, {start[1]:.1f}) to ({end[0]:.1f}, {end[1]:.1f})."
    )
    return CrossSection(
        distances, heights, View("cross_section", _profile_png(distances, heights), facts, notes)
    )


def inspect_elevation(grid: TerrainGrid, polygon: Ring) -> dict[str, float]:
    """Ground and slope statistics for the cells whose centres are inside ``polygon``."""
    rows, cols = grid.dem.shape
    xs = grid.bbox[0] + (np.arange(cols, dtype=np.float64) + 0.5) * grid.cell_m
    ys = grid.bbox[3] - (np.arange(rows, dtype=np.float64) + 0.5) * grid.cell_m
    x, y = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(Polygon(polygon), x, y)
    if not inside.any():
        raise ValueError("no cell centre of the terrain grid is inside the polygon")
    ground = grid.dem[inside]
    slope = slope_degrees(grid)[inside]
    return {
        "cells": float(inside.sum()),
        "min_m": float(ground.min()),
        "max_m": float(ground.max()),
        "mean_m": float(ground.mean()),
        "relief_m": float(ground.max() - ground.min()),
        "mean_slope_deg": float(slope.mean()),
        "max_slope_deg": float(slope.max()),
        "max_above_ground_m": float(grid.ndsm[inside].max()),
    }


def _height_at(grid: TerrainGrid, point: Point) -> float:
    rows, cols = grid.dem.shape
    col = float(np.clip((point[0] - grid.bbox[0]) / grid.cell_m - 0.5, 0, cols - 1))
    row = float(np.clip((grid.bbox[3] - point[1]) / grid.cell_m - 0.5, 0, rows - 1))
    c0, r0 = min(int(col), max(cols - 2, 0)), min(int(row), max(rows - 2, 0))
    c1, r1 = min(c0 + 1, cols - 1), min(r0 + 1, rows - 1)
    fc, fr = col - c0, row - r0
    d = grid.dem
    top = d[r0, c0] * (1 - fc) + d[r0, c1] * fc
    bottom = d[r1, c0] * (1 - fc) + d[r1, c1] * fc
    return float(top * (1 - fr) + bottom * fr)


def _profile_png(distances: list[float], heights: list[float]) -> bytes:
    width, height, pad = 640, 240, 24
    low, high = min(heights), max(heights)
    span = max(high - low, 0.5)  # don't magnify sub-decimetre noise into cliffs
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    length = distances[-1] or 1.0
    line = [
        (pad + (width - 2 * pad) * d / length, height - pad - (height - 2 * pad) * (h - low) / span)
        for d, h in zip(distances, heights, strict=True)
    ]
    draw.line(line, fill=(40, 90, 40), width=3)
    draw.text((pad, 4), f"{high:.2f} m", fill="black")
    draw.text((pad, height - pad + 4), f"{low:.2f} m   length {length:.1f} m", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
