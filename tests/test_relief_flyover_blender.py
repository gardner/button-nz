"""Tier 2 in real Blender: the photo draped on the DSM, flown over."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from button_nz.relief import SiteRelief
from button_nz.relief.flyover import FlyoverSettings, render_flyover

pytestmark = pytest.mark.blender


def test_renders_every_frame_starting_from_the_photo(tmp_path: Path) -> None:
    surface = np.zeros((20, 20))
    surface[8:12, 8:12] = 4.0  # a building in the middle
    aerial = np.zeros((80, 80, 3), dtype=np.uint8)
    aerial[:] = (40, 160, 40)  # grass
    aerial[32:48, 32:48] = (200, 30, 30)  # its red roof
    relief = SiteRelief(aerial, surface, 1.0, 0.25, (0.0, 0.0, 20.0, 20.0))
    settings = FlyoverSettings(frames=3, width=64, height=36, tilt_deg=40, orbit_deg=60)
    frames = render_flyover(relief, tmp_path, settings)
    assert len(frames) == 3
    first = np.asarray(Image.open(frames[0]).convert("RGB"))
    assert first.shape == (36, 64, 3)
    # Straight overhead, the frame's centre is the red roof, in the photo's own colour.
    assert np.abs(first[18, 32].astype(int) - (200, 30, 30)).max() <= 6
    last = np.asarray(Image.open(frames[-1]).convert("RGB"))
    assert not np.array_equal(first, last)
