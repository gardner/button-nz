"""LiDAR views and measurements a design model can request (plan §7): new
representations of the measured terrain, never new information."""

from button_nz.lidar.analysis import (
    CrossSection,
    cross_section,
    inspect_elevation,
    normals,
    slope_degrees,
)
from button_nz.lidar.render import View
from button_nz.lidar.views import contours, hillshade, ndsm_map, normal_map, overlay, slope_map

__all__ = [
    "CrossSection",
    "View",
    "contours",
    "cross_section",
    "hillshade",
    "inspect_elevation",
    "ndsm_map",
    "normal_map",
    "normals",
    "overlay",
    "slope_degrees",
    "slope_map",
]
