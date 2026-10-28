"""Tests for button_nz.bench.questions: Experiment A's ground truth, checked
against synthetic terrains whose answers are known in closed form."""

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.agent.site import DesignSite
from button_nz.bench.questions import Mark, Question, _mean_slope, _Terrain, generate, score  # pyright: ignore[reportPrivateUsage]
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import SiteContext
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

# One 60 m x 40 m parcel over a 70 m x 50 m grid of 1 m cells; local origin at its centre.
PARCEL: Ring = ((5.0, 5.0), (65.0, 5.0), (65.0, 45.0), (5.0, 45.0), (5.0, 5.0))


def site(dem: NDArray[np.float64]) -> DesignSite:
    grid = TerrainGrid((0.0, 0.0, 70.0, 50.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame.centred_on(grid.bbox)
    return DesignSite(
        scene_input(grid, frame, [PARCEL]), frame, SiteContext(parcels=(PARCEL,), terrain=grid)
    )


def centres() -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    xs = np.arange(70, dtype=np.float64) + 0.5
    ys = 50 - (np.arange(50, dtype=np.float64) + 0.5)
    return np.meshgrid(xs, ys)


def plane(east: float, north: float) -> DesignSite:
    x, y = centres()
    return site(100.0 + east * x + north * y)


def of_kind(questions: list[Question], kind: str) -> list[Question]:
    found = [q for q in questions if q.kind == kind]
    assert found, f"no {kind} questions"
    return found


@pytest.mark.parametrize(
    ("east", "north", "downhill"),
    [(0.1, 0.0, "W"), (-0.1, 0.0, "E"), (0.0, 0.1, "S"), (0.1, 0.1, "SW"), (-0.1, 0.1, "SE")],
)
def test_aspect_is_the_downhill_direction(east: float, north: float, downhill: str) -> None:
    for question in of_kind(generate(plane(east, north), per_kind=5, seed=1), "aspect"):
        assert question.answer == downhill
        assert downhill in question.choices


def test_height_differences_follow_the_plane() -> None:
    for q in of_kind(generate(plane(0.1, 0.0), per_kind=5, seed=2), "height_difference"):
        a, b = q.marks
        assert q.answer == pytest.approx(0.1 * (a.x - b.x), abs=1e-6)
        assert abs(float(q.answer)) >= 0.3  # big enough to see


def test_relief_of_a_square_on_a_plane() -> None:
    for q in of_kind(generate(plane(0.1, 0.0), per_kind=3, seed=3), "relief"):
        (area,) = q.marks
        assert q.answer == pytest.approx(0.1 * 2 * area.half_m, abs=1e-6)


def test_the_steepest_area_is_the_one_on_the_bank() -> None:
    """Flat ground with a 0.4 m/m bank between x = 40 and 50 (NZTM)."""
    x, _ = centres()
    dem = 100.0 + 0.4 * np.clip(x - 40.0, 0.0, 10.0)
    for q in of_kind(generate(site(dem), per_kind=5, seed=4), "steepest"):
        steepest = next(m for m in q.marks if m.label == q.answer)
        # The bank is local x 5..15 (origin at NZTM x 35): the steepest square overlaps it.
        assert steepest.x + steepest.half_m > 5.0 and steepest.x - steepest.half_m < 15.0


def test_flat_ground_asks_no_aspect_or_steepness_question() -> None:
    """Ambiguous answers are left out rather than guessed."""
    asked = {q.kind for q in generate(site(np.full((50, 70), 100.0)), per_kind=5, seed=5)}
    assert "aspect" not in asked and "steepest" not in asked


def test_questions_are_reproducible_and_inside_the_title() -> None:
    first = generate(plane(0.1, 0.05), per_kind=4, seed=7)
    assert first == generate(plane(0.1, 0.05), per_kind=4, seed=7)
    for question in first:
        for mark in question.marks:
            # Local frame origin is NZTM (35, 25); the parcel spans local -30..30, -20..20.
            assert mark.x - mark.half_m >= -30 and mark.x + mark.half_m <= 30
            assert mark.y - mark.half_m >= -20 and mark.y + mark.half_m <= 20
        assert question.text and question.id


def test_scoring() -> None:
    choice = Question("q1", "aspect", "?", (), "SW", choices=("N", "SW"))
    assert score(choice, " sw ") and not score(choice, "S")
    number = Question("q2", "relief", "?", (), 1.5, tolerance=0.2)
    assert score(number, "1.62") and score(number, "about 1.4 m") is False
    assert score(number, "1.4") and not score(number, "1.75")
    assert not score(number, "nan") and not score(number, "")


def test_numeric_answers_are_rounded_for_asking() -> None:
    for q in generate(plane(0.1, 0.0), per_kind=3, seed=8):
        if isinstance(q.answer, float):
            assert math.isfinite(q.answer)


def test_steepness_averages_slope_angles_as_the_views_report_them() -> None:
    """Mean of per-sample degrees (as inspect_elevation's mean_slope_deg), not atan of
    the mean grade: they rank a square of mixed flat and steep ground differently."""
    x, _ = centres()
    dem = 100.0 + 1.5 * np.clip(x - 40.0, 0.0, 2.0)  # a steep 2 m band
    terrain = _Terrain(site(dem))
    square = Mark("1", 5.0, 0.0, 2.5)  # local x 2.5..7.5 covers NZTM 37.5..42.5
    grades = [math.hypot(*terrain.gradient(x, y)) for x, y in terrain.lattice(square)]
    expected = sum(math.degrees(math.atan(g)) for g in grades) / len(grades)
    assert _mean_slope(terrain, square) == pytest.approx(expected)
