"""Tests for scripts/demo/record.py's reading of the page: when the shown
design has ended, and how. The live run itself isn't tested (it's paid)."""

import inspect
from pathlib import Path

import pytest

from button_nz.relief.flyover import render_flyover
from record import (
    ORBIT_PX,
    RELIEF_LIMIT_S,
    fixed_by,
    orbit_path,
    outcome,
    partial_path,
    placed_name,
)

FEEDBACK = "Blender did not finish with your design: it crashed while running your script."


@pytest.mark.parametrize(
    ("text", "ended"),
    [
        ("Queued…", None),
        ("Muse is designing: reading the LiDAR, writing Blender, checking… " + FEEDBACK, None),
        ("Accepted: attempt 2 Attempt 1 error " + FEEDBACK, "accepted"),
        ("No attempt passed every check.", "no attempt passed every check"),
        ("The design run failed: KeyError: META_API_KEY", "the design run failed"),
        ("Brief Design", None),  # nothing started yet
    ],
)
def test_the_shown_design_ends_on_its_status_line_not_on_words_in_feedback(
    text: str, ended: str | None
) -> None:
    assert outcome(text) == ended


def test_a_failed_take_is_kept_beside_the_one_asked_for() -> None:
    assert partial_path(Path("out/demo-raw.webm")) == Path("out/demo-raw-partial.webm")


@pytest.mark.parametrize(
    ("text", "who"),
    [
        (
            "What's on the site? Fixed on this server, as the owner decided it.",
            "the owner",
        ),
        ("What is on the site #1 shed Existing building Keep clear Ignore", None),
    ],
)
def test_the_take_reads_who_fixed_the_survey(text: str, who: str | None) -> None:
    assert fixed_by(text) == who


def test_the_take_reads_which_product_a_button_places() -> None:
    assert placed_name("Place the AirHome Vista on the site") == "AirHome Vista"


def test_the_recorder_waits_for_the_fly_over_as_long_as_the_server_may_render_it() -> None:
    render_s = inspect.signature(render_flyover).parameters["timeout_s"].default
    assert render_s <= RELIEF_LIMIT_S


def test_the_town_orbit_eases_in_and_out_and_ends_where_it_turned_to() -> None:
    path = orbit_path(10.0, fps=30)
    assert len(path) == 301 and path[0] == (0.0, 0.0)
    assert path[-1][0] == pytest.approx(ORBIT_PX) and path[-1][1] == pytest.approx(0, abs=1e-9)
    steps = [b[0] - a[0] for a, b in zip(path, path[1:], strict=False)]
    assert steps[0] < steps[150] and steps[-1] < steps[150]  # slow at both ends


def test_the_town_orbit_tilts_down_and_back_clear_of_the_maps_max_pitch() -> None:
    # Moving down lowers the pitch: from 60° it falls and comes back, well under maxPitch 70°.
    dys = [dy for _, dy in orbit_path(10.0, fps=30)]
    assert min(dys) >= 0 and max(dys) > 0
