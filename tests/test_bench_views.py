"""Tests for button_nz.bench.views: what each Experiment A condition shows."""

import io

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from button_nz.agent.site import DesignSite
from button_nz.bench.questions import Mark, Question
from button_nz.bench.views import CONDITIONS, MARK_COLOUR, SCALE, condition_images
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

PARCEL: Ring = ((5.0, 5.0), (35.0, 5.0), (35.0, 25.0), (5.0, 25.0), (5.0, 5.0))


@pytest.fixture
def site() -> DesignSite:
    """40 m x 30 m of ground rising east; the local origin is its centre, NZTM (20, 15)."""
    x = np.tile(np.arange(40, dtype=np.float64) + 0.5, (30, 1))
    grid = TerrainGrid((0.0, 0.0, 40.0, 30.0), 1.0, 100.0 + 0.1 * x, np.zeros_like(x), ("t",))
    frame = LocalFrame.centred_on(grid.bbox)
    return DesignSite(
        scene_input(grid, frame, [PARCEL]), frame, SiteContext(parcels=(PARCEL,), terrain=grid)
    )


@pytest.fixture
def aerial() -> NDArray[np.uint8]:
    return np.full((30 * SCALE, 40 * SCALE, 3), 128, dtype=np.uint8)


QUESTION = Question("q", "aspect", "?", (Mark("A", 0.0, 0.0),), "W", ("W",))


def pixels(png: bytes) -> NDArray[np.uint8]:
    image: NDArray[np.uint8] = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    return image


@pytest.mark.parametrize(
    ("condition", "count"),
    [("aerial", 1), ("aerial_contours", 2), ("aerial_ndsm_slope", 3), ("agent", 1)],
)
def test_each_condition_shows_its_views(
    site: DesignSite, aerial: NDArray[np.uint8], condition: str, count: int
) -> None:
    images = condition_images(condition, QUESTION, site, aerial)
    assert len(images) == count
    assert images[0][0].startswith("Aerial photograph")
    assert all(png.startswith(b"\x89PNG") for _, png in images)
    assert set(CONDITIONS) == {"aerial", "aerial_contours", "aerial_ndsm_slope", "agent"}


def test_marks_are_drawn_where_their_local_coordinates_are(
    site: DesignSite, aerial: NDArray[np.uint8]
) -> None:
    """Local (0, 0) is NZTM (20, 15): the middle of the 40 m x 30 m image."""
    for _, png in condition_images("aerial_ndsm_slope", QUESTION, site, aerial):
        image = pixels(png)
        assert image.shape[:2] == (30 * SCALE, 40 * SCALE)
        assert tuple(image[15 * SCALE, 20 * SCALE]) == MARK_COLOUR


def test_a_square_mark_is_outlined(site: DesignSite, aerial: NDArray[np.uint8]) -> None:
    square = Question("q", "relief", "?", (Mark("A", 0.0, 0.0, half_m=5.0),), 1.0)
    (_, png), *_ = condition_images("aerial", square, site, aerial)
    image = pixels(png)
    assert tuple(image[15 * SCALE, 15 * SCALE]) == MARK_COLOUR  # west edge, x = 15 NZTM
    assert tuple(image[15 * SCALE, 25 * SCALE]) == MARK_COLOUR  # east edge
    assert tuple(image[12 * SCALE, 20 * SCALE]) == (128, 128, 128)  # inside: untouched


def test_an_aerial_of_the_wrong_size_raises(site: DesignSite) -> None:
    with pytest.raises(ValueError, match="aerial"):
        condition_images("aerial", QUESTION, site, np.zeros((10, 10, 3), dtype=np.uint8))
