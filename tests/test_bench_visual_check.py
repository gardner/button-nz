"""Tests for button_nz.bench.visual_check: it measures the attempt the app illustrates."""

import json
from pathlib import Path

import pytest

from button_nz.bench.visual_check import accepted_attempt, keep
from button_nz.perception.visual import VISUAL_MODEL, Visual


def _run(runs: Path, design: str, accepted: int | None) -> None:
    (runs / design).mkdir(parents=True)
    summary: dict[str, object] = {"brief": "b", "accepted_attempt": accepted, "attempts": []}
    (runs / design / "design.json").write_text(json.dumps(summary), encoding="utf-8")


def test_the_accepted_attempt_is_measured_not_the_first(tmp_path: Path) -> None:
    _run(tmp_path, "d2", 2)  # attempt 1 was rejected: its render isn't the design
    assert accepted_attempt(tmp_path, "d2") == tmp_path / "d2" / "attempt-2"


def test_a_design_with_no_accepted_attempt_is_refused(tmp_path: Path) -> None:
    _run(tmp_path, "none", None)
    with pytest.raises(ValueError, match="no accepted attempt"):
        accepted_attempt(tmp_path, "none")


def test_each_visual_can_be_kept_for_review(tmp_path: Path) -> None:
    """The app keeps only accepted pictures; a measurement can keep its record too."""
    visual = Visual(VISUAL_MODEL, True, 0.8, None, b"\x89PNG close-up", 1, (1, 2, 3, 4))
    keep(visual, tmp_path / "kept", "d1")
    assert (tmp_path / "kept" / "d1" / "visual.png").read_bytes() == b"\x89PNG close-up"
    assert json.loads((tmp_path / "kept" / "d1" / "visual.json").read_text())["iou"] == 0.8
