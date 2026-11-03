"""The fly-over's camera: where it is and which way it looks, frame by frame."""

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.relief.camera import CameraPose, fitting_distance, flyover_path


def _looks(pose: CameraPose) -> NDArray[np.float64]:
    """Blender's view direction (its camera looks down local -z) for an XYZ euler."""
    x, y, z = pose.rotation
    rx = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rz = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rz @ ry @ rx @ np.array([0.0, 0.0, -1.0])


def test_starts_straight_overhead() -> None:
    first = flyover_path(10, (1.0, 2.0, 3.0), 50.0, tilt_deg=40, orbit_deg=90, bearing_deg=0)[0]
    assert first.location == pytest.approx((1.0, 2.0, 53.0))
    assert _looks(first) == pytest.approx([0.0, 0.0, -1.0])


def test_looks_at_the_target_from_every_frame() -> None:
    target = (5.0, -3.0, 10.0)
    for pose in flyover_path(12, target, 40.0, tilt_deg=45, orbit_deg=120, bearing_deg=30):
        towards = np.subtract(target, pose.location)
        assert np.linalg.norm(towards) == pytest.approx(40.0)
        assert _looks(pose) == pytest.approx(towards / 40.0, abs=1e-9)


def test_tilts_down_then_orbits() -> None:
    path = flyover_path(11, (0.0, 0.0, 0.0), 10.0, tilt_deg=45, orbit_deg=90, bearing_deg=0)
    tilted = path[4]  # the tilt is done by 40% of the way
    assert _looks(tilted) == pytest.approx([0.0, math.sqrt(0.5), -math.sqrt(0.5)])  # north
    last = path[-1]  # orbited 90 degrees clockwise: looking east
    assert _looks(last) == pytest.approx([math.sqrt(0.5), 0.0, -math.sqrt(0.5)])


def test_the_distance_fits_the_site_in_the_frame() -> None:
    # A 36 mm sensor behind a 18 mm lens sees 90 degrees across: 2 m wide at 1 m.
    assert fitting_distance(40.0, 10.0, aspect=16 / 9, lens_mm=18, sensor_mm=36) == pytest.approx(
        20.0
    )
    # A deep site fits by its depth instead: 36 m deep needs 64 m across.
    assert fitting_distance(40.0, 36.0, aspect=16 / 9, lens_mm=18, sensor_mm=36) == pytest.approx(
        32.0
    )
