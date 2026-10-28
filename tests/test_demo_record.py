"""Tests for scripts/demo/record.py's reading of the page: when the shown
design has ended, and how. The live run itself isn't tested (it's paid)."""

from pathlib import Path

import pytest

from record import outcome, partial_path

FEEDBACK = "Blender did not finish with your design: it crashed while running your script."


@pytest.mark.parametrize(
    ("text", "ended"),
    [
        ("Design queued…", None),
        ("Design running… Attempt 1 fail " + FEEDBACK, None),
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
