"""Tests for scripts/demo/record.py's reading of the page: when the shown
design has ended, and how. The live run itself isn't tested (it's paid)."""

from pathlib import Path

import pytest

from record import fixed_by, outcome, partial_path, placed_name

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
