"""Measurements from the terrain grid: slope, normals, cross-sections and
elevation statistics. Coordinates are NZTM metres; heights NZVD2016."""

import io
import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import shapely
from numpy.typing import NDArray
from PIL import Image, ImageDraw
from shapely import Polygon

from button_nz.blender_worker.terrain_math import height_at
from button_nz.geo.geometry import Point, Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.lidar.render import View

EDGE_TOLERANCE_M = 1e-6


class NoCellsInside(ValueError):
    """The polygon is real, but too small to contain a cell centre."""


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


def cross_section(
    grid: TerrainGrid, start: Point, end: Point, step_m: float = 0.5, datum_m: float = 0.0
) -> CrossSection:
    """The terrain along the line ``start``-``end``, sampled every ``step_m`` on
    the terrain mesh's own triangles (``terrain_math.height_at``). Both ends must
    lie within the cell centres: the grid measures nothing beyond them. Heights
    and facts are NZVD2016; the picture is labelled in metres above ``datum_m``."""
    for point in (start, end):
        if not _on_grid(grid, point):
            raise ValueError(f"({point[0]:.1f}, {point[1]:.1f}) is outside the terrain grid")
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    n = max(1, math.ceil(length / step_m))
    distances = [length * i / n for i in range(n + 1)]
    points = [
        (start[0] + (end[0] - start[0]) * d / length, start[1] + (end[1] - start[1]) * d / length)
        if length
        else start
        for d in distances
    ]
    surface = _surface(grid)
    heights = [height_at(surface, x, y) for x, y in points]
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
        distances,
        heights,
        View(
            "cross_section",
            _profile_png(distances, [h - datum_m for h in heights]),
            facts,
            notes,
        ),
    )


def inspect_elevation(grid: TerrainGrid, polygon: Ring) -> dict[str, float]:
    """Ground and slope statistics for the cells whose centres are inside
    ``polygon``, which must lie within the grid's cell centres."""
    for point in polygon:
        if not _on_grid(grid, point):
            raise ValueError(f"({point[0]:.1f}, {point[1]:.1f}) is outside the terrain grid")
    rows, cols = grid.dem.shape
    xs = grid.bbox[0] + (np.arange(cols, dtype=np.float64) + 0.5) * grid.cell_m
    ys = grid.bbox[3] - (np.arange(rows, dtype=np.float64) + 0.5) * grid.cell_m
    x, y = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(Polygon(polygon), x, y)
    if not inside.any():
        raise NoCellsInside("no cell centre of the terrain grid is inside the polygon")
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


def _on_grid(grid: TerrainGrid, point: Point) -> bool:
    """Within the cell centres, allowing for the rounding of a local-to-NZTM trip."""
    half, e = grid.cell_m / 2, EDGE_TOLERANCE_M
    west, south, east, north = grid.bbox
    return (
        west + half - e <= point[0] <= east - half + e
        and south + half - e <= point[1] <= north - half + e
    )


def _surface(grid: TerrainGrid) -> dict[str, Any]:
    """``grid`` as the scene's terrain description, for ``height_at``."""
    rows, cols = grid.dem.shape
    return {
        "x0": grid.bbox[0] + grid.cell_m / 2,
        "y0": grid.bbox[3] - grid.cell_m / 2,
        "cell_m": grid.cell_m,
        "rows": rows,
        "cols": cols,
        "heights": grid.dem.ravel().tolist(),
    }


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
