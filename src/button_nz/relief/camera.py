"""The fly-over's camera path, as Blender poses: plain maths, so it is tested
without Blender.

The camera is tilted ``tilt_deg`` from straight down, looking towards
``bearing_deg`` at the first frame, and orbits the target once clockwise at
an even speed, always ``distance_m`` from it and looking at it. The last
frame is one step before the first, so the clip loops without a jump. A
Blender camera looks down its local -z with +y up; turning it about x by
the tilt, then about z by minus the bearing, points it the right way.
"""

import math
from dataclasses import dataclass

type Vector = tuple[float, float, float]


@dataclass(frozen=True)
class CameraPose:
    location: Vector
    rotation: Vector  # Blender XYZ Euler, radians


def flyover_path(
    frames: int, target: Vector, distance_m: float, tilt_deg: float, bearing_deg: float
) -> list[CameraPose]:
    tilt = math.radians(tilt_deg)
    turns = (math.radians(bearing_deg + 360 * frame / frames) for frame in range(frames))
    return [_pose(target, distance_m, tilt, bearing) for bearing in turns]


def fitting_distance(
    width_m: float, height_m: float, aspect: float, lens_mm: float, sensor_mm: float
) -> float:
    """How far straight overhead a camera must be for a ``width_m`` x
    ``height_m`` site to fill its frame (``aspect`` wide to 1 high, the
    sensor's width ``sensor_mm``) across or down, whichever is tighter."""
    across = max(width_m, height_m * aspect)
    return across / 2 * lens_mm / (sensor_mm / 2)


def _pose(target: Vector, distance_m: float, tilt: float, bearing: float) -> CameraPose:
    looks = (
        math.sin(bearing) * math.sin(tilt),
        math.cos(bearing) * math.sin(tilt),
        -math.cos(tilt),
    )
    location = (
        target[0] - distance_m * looks[0],
        target[1] - distance_m * looks[1],
        target[2] - distance_m * looks[2],
    )
    return CameraPose(location, (tilt, 0.0, -bearing))
