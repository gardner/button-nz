"""Tests for the pure parts of scripts/demo/screencast.py: no browser, no ffmpeg."""

import base64
import json
from pathlib import Path

import pytest

from demo.screencast import (
    encode_command,
    find_chromium,
    frame_event,
    marks_document,
    tick_frames,
)


def test_each_tick_shows_the_latest_frame_captured_by_then() -> None:
    # Frames at 0.0, 0.25 and 0.6 s; ticks every 0.2 s up to 1.0 s.
    assert tick_frames([0.0, 0.25, 0.6], end=1.0, fps=5) == [0, 0, 1, 2, 2]


def test_a_frame_exactly_on_a_tick_is_used_for_that_tick() -> None:
    assert tick_frames([0.0, 0.5], end=1.0, fps=2) == [0, 1]


def test_ticks_before_the_first_frame_show_the_first_frame() -> None:
    assert tick_frames([0.3, 0.9], end=0.8, fps=5) == [0, 0, 0, 0]


def test_a_long_static_wait_repeats_the_last_frame_to_keep_the_rate() -> None:
    assert tick_frames([0.0], end=2.0, fps=3) == [0] * 6


def test_no_frames_means_no_ticks() -> None:
    assert tick_frames([], end=5.0, fps=15) == []


def test_frame_event_decodes_the_jpeg_and_session() -> None:
    event: dict[str, object] = {"data": base64.b64encode(b"jpeg").decode(), "sessionId": 7}
    assert frame_event(event) == (b"jpeg", 7)


@pytest.mark.parametrize(
    "event",
    [
        None,
        {"data": "aGk="},
        {"sessionId": 1},
        {"data": 3, "sessionId": 1},
        {"data": "aGk=", "sessionId": "1"},
    ],
)
def test_frame_event_rejects_malformed_cdp_events(event: object) -> None:
    with pytest.raises(TypeError):
        frame_event(event)


def test_encode_command_reads_a_file_and_encodes_vp9(tmp_path: Path) -> None:
    command = encode_command(Path("/ff"), tmp_path / "in.mjpeg", 15, tmp_path / "out.webm")
    assert command[0] == "/ff"
    assert command[command.index("-i") + 1] == str(tmp_path / "in.mjpeg")
    assert command[command.index("-framerate") + 1] == "15"
    assert command[command.index("-c:v", command.index("-i")) + 1] == "libvpx-vp9"
    assert command[-1] == str(tmp_path / "out.webm")


def test_marks_document_round_trips_through_json() -> None:
    document = marks_document(476.94, [(3.0, "the site")])
    assert json.loads(json.dumps(document)) == {"seconds": 476.9, "marks": [[3.0, "the site"]]}


def test_find_chromium_takes_the_newest_headless_shell(tmp_path: Path) -> None:
    for version in ("1200", "1248"):
        shell = (
            tmp_path
            / f"chromium_headless_shell-{version}"
            / "chrome-linux"
            / "chrome-headless-shell"
        )
        shell.parent.mkdir(parents=True)
        shell.touch()
    assert find_chromium(tmp_path).parts[-3] == "chromium_headless_shell-1248"


def test_find_chromium_says_when_playwright_has_not_installed_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="playwright install"):
        find_chromium(tmp_path)
