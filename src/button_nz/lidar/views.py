"""Map views of the terrain grid, each on a fixed scale so colours mean the same
thing every time. These re-present the LiDAR measurements; they add no data."""

import math

import numpy as np

from button_nz.geo.terrain import TerrainGrid
from button_nz.lidar.analysis import normals, slope_degrees
from button_nz.lidar.render import View, colour_scale, grey, to_png

SLOPE_SCALE_DEG = (0.0, 30.0)
NDSM_SCALE_M = (0.0, 15.0)


def hillshade(
    grid: TerrainGrid, azimuth_deg: float = 315.0, altitude_deg: float = 45.0, scale: int = 8
) -> View:
    """The ground lit by a sun at ``azimuth_deg`` (clockwise from north) and
    ``altitude_deg`` above the horizon: shows banks, ridges and hollows."""
    az, alt = math.radians(azimuth_deg), math.radians(altitude_deg)
    sun = np.array([math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)])
    shade = np.clip(normals(grid) @ sun, 0.0, 1.0)
    facts = {"azimuth_deg": azimuth_deg, "altitude_deg": altitude_deg}
    notes = f"Hillshade, sun from {azimuth_deg:g}° at {altitude_deg:g}° altitude."
    return View("hillshade", to_png(grey(shade), scale), facts, notes)


def contours(grid: TerrainGrid, interval_m: float = 0.5, scale: int = 8) -> View:
    """Dark lines every ``interval_m`` of elevation over a light elevation tint."""
    band = np.floor(grid.dem / interval_m)
    line = np.zeros(band.shape, dtype=bool)
    line[:, :-1] |= band[:, :-1] != band[:, 1:]
    line[:-1, :] |= band[:-1, :] != band[1:, :]
    low, high = float(grid.dem.min()), float(grid.dem.max())
    tint = 0.75 + 0.2 * (grid.dem - low) / max(high - low, 1e-9)
    rgb = grey(tint)
    rgb[line] = (20, 20, 20)
    facts = {"interval_m": interval_m, "min_m": low, "max_m": high}
    notes = f"Contours every {interval_m:g} m, from {low:.2f} m to {high:.2f} m (NZVD2016)."
    return View("contours", to_png(rgb, scale), facts, notes)


def slope_map(grid: TerrainGrid, scale: int = 8) -> View:
    slope = slope_degrees(grid)
    facts = {
        "min_slope_deg": float(slope.min()),
        "max_slope_deg": float(slope.max()),
        "mean_slope_deg": float(slope.mean()),
    }
    low, high = SLOPE_SCALE_DEG
    notes = f"Slope in degrees, scale {low:g}° (dark) to {high:g}° (yellow) or steeper."
    return View("slope", to_png(colour_scale(slope, low, high), scale), facts, notes)


def ndsm_map(grid: TerrainGrid, scale: int = 8) -> View:
    """Above-ground height (DSM - DEM): evidence of structures or vegetation,
    not modelled buildings or trees."""
    facts = {
        "max_above_ground_m": float(grid.ndsm.max()),
        "cells_over_2m": float((grid.ndsm > 2.0).sum()),
    }
    low, high = NDSM_SCALE_M
    notes = (
        f"Height above ground, {low:g} m (dark) to {high:g} m (yellow). Measured surface "
        "differences, not exact building or tree heights."
    )
    return View("ndsm", to_png(colour_scale(grid.ndsm, low, high), scale), facts, notes)


def normal_map(grid: TerrainGrid, scale: int = 8) -> View:
    """Surface normals as colour: red = east, green = north, blue = up."""
    n = normals(grid)
    rgb = ((n + 1.0) / 2.0 * 255).round().astype(np.uint8)
    facts = {"mean_up_component": float(n[..., 2].mean())}
    notes = "Surface normals: red east, green north, blue up; flat ground is light blue."
    return View("normals", to_png(rgb, scale), facts, notes)
