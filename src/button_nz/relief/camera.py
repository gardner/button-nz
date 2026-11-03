"""The fly-over's camera path, as Blender poses: plain maths, so it is tested
without Blender.

The camera starts straight over the target, tilts down towards
``bearing_deg`` (the first 40% of the frames), then orbits clockwise by
``orbit_deg`` (the rest), always ``distance_m`` from the target and looking at
it. A Blender camera looks down its local -z with +y up; turning it about x by
the tilt, then about z by minus the bearing, points it the right way.
"""

import math
from dataclasses import dataclass

type Vector = tuple[float, float, float]

TILT_SHARE = 0.4  # of the frames, spent tilting down before the orbit


@dataclass(frozen=True)
class CameraPose:
    location: Vector
    rotation: Vector  # Blender XYZ Euler, radians


def flyover_path(
    frames: int,
    target: Vector,
    distance_m: float,
    tilt_deg: float,
    orbit_deg: float,
    bearing_deg: float,
) -> list[CameraPose]:
    poses: list[CameraPose] = []
    for frame in range(frames):
        t = frame / max(frames - 1, 1)
        tilt = tilt_deg * _ease(min(t / TILT_SHARE, 1.0))
        orbit = orbit_deg * _ease(max(t - TILT_SHARE, 0.0) / (1 - TILT_SHARE))
        poses.append(
            _pose(target, distance_m, math.radians(tilt), math.radians(bearing_deg + orbit))
        )
    return poses


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


def _ease(t: float) -> float:
    return (1 - math.cos(math.pi * t)) / 2
