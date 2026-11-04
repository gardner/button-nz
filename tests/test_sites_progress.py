"""Tests for button_nz.sites.progress: what each step of a site's build shows
while the site is built, written as each step finishes."""

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.features import Mask
from button_nz.perception.survey import CONCEPTS
from button_nz.sites.progress import (
    PROGRESS_FILE,
    TERRAIN_PREVIEW,
    TERRAIN_PX_PER_M,
    BuildProgress,
    read_progress,
    terrain_preview,
)

BBOX = (1000.0, 2000.0, 1040.0, 2030.0)  # 40 m by 30 m
RING = ((1010.0, 2010.0), (1020.0, 2010.0), (1020.0, 2020.0), (1010.0, 2010.0))


def grid(ndsm: float = 0.0) -> TerrainGrid:
    rows, cols = 30, 40
    dem = np.tile(np.linspace(100.0, 110.0, cols), (rows, 1))  # rising to the east
    return TerrainGrid(BBOX, 1.0, dem, np.full((rows, cols), ndsm), ("dem", "dsm"))


def test_nothing_is_shown_before_the_parcels_are_found(tmp_path: Path) -> None:
    assert read_progress(tmp_path) == {
        "frame": None,
        "parcels": [],
        "buildings": [],
        "terrain": None,
        "aerial": None,
        "survey": None,
    }


def test_the_parcels_set_the_frame_and_are_kept_as_rings(tmp_path: Path) -> None:
    BuildProgress(tmp_path).parcels(BBOX, [RING], [RING, RING])
    shown = read_progress(tmp_path)
    assert shown["frame"] == list(BBOX)
    assert shown["parcels"] == [[list(p) for p in RING]]
    assert len(shown["buildings"]) == 2


def test_the_terrain_is_an_image_of_its_heights_with_their_range(tmp_path: Path) -> None:
    progress = BuildProgress(tmp_path)
    progress.parcels(BBOX, [RING], [])
    progress.terrain(grid(ndsm=2.0))
    shown = read_progress(tmp_path)
    assert shown["terrain"] == {"bbox": list(BBOX), "low_m": 102.0, "high_m": 112.0}
    with Image.open(tmp_path / TERRAIN_PREVIEW) as image:
        assert image.mode == "RGB"
        assert image.size == (40 * TERRAIN_PX_PER_M, 30 * TERRAIN_PX_PER_M)


def test_the_terrain_preview_is_the_same_for_the_same_heights() -> None:
    assert terrain_preview(grid()) == terrain_preview(grid())


def test_the_terrain_preview_tints_high_ground_apart_from_low() -> None:
    with Image.open(io.BytesIO(terrain_preview(grid()))) as image:
        pixels = np.asarray(image, dtype=np.int16)
    west, east = pixels[60, 8], pixels[60, -8]
    assert np.abs(west - east).sum() > 60


def test_a_flat_site_is_still_shown(tmp_path: Path) -> None:
    flat = TerrainGrid(BBOX, 1.0, np.full((30, 40), 50.0), np.zeros((30, 40)), ())
    BuildProgress(tmp_path).terrain(flat)
    assert read_progress(tmp_path)["terrain"]["low_m"] == 50.0


def test_the_aerial_is_shown_over_its_bbox(tmp_path: Path) -> None:
    BuildProgress(tmp_path).aerial(BBOX)
    assert read_progress(tmp_path)["aerial"] == {"bbox": list(BBOX)}


def test_the_survey_shows_each_concept_as_sam_is_asked_and_answers(tmp_path: Path) -> None:
    progress = BuildProgress(tmp_path)
    seen: list[dict[str, object]] = []

    def segment(image: np.ndarray, concept: str) -> list[Mask]:
        seen.append(read_progress(tmp_path)["survey"])
        if concept != "tree":
            return []
        pixels = np.zeros((240, 320), dtype=bool)
        pixels[80:160, 80:160] = True  # 10 m square, at 0.125 m a pixel
        return [Mask("tree", 0.9, pixels)]

    watched = progress.watching(segment, grid(ndsm=6.0), BBOX, 0.125)
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    for concept in CONCEPTS:
        watched(image, concept)
    assert seen[0] == {"concepts": list(CONCEPTS), "asking": CONCEPTS[0], "found": []}
    survey = read_progress(tmp_path)["survey"]
    assert survey["asking"] is None
    assert [f["concept"] for f in survey["found"]] == list(CONCEPTS)
    trees = next(f for f in survey["found"] if f["concept"] == "tree")
    assert len(trees["rings"]) == 1
    xs = [x for x, _ in trees["rings"][0]]
    assert min(xs) == 1010.0 and max(xs) == 1020.0


def test_what_a_step_shows_is_never_half_written(tmp_path: Path) -> None:
    BuildProgress(tmp_path).parcels(BBOX, [RING], [])
    assert [p.name for p in tmp_path.iterdir()] == [PROGRESS_FILE]
    json.loads((tmp_path / PROGRESS_FILE).read_text())


def test_a_new_build_starts_with_nothing_shown_from_the_last(tmp_path: Path) -> None:
    BuildProgress(tmp_path).parcels(BBOX, [RING], [])
    BuildProgress(tmp_path)
    assert read_progress(tmp_path)["frame"] is None
