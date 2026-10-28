"""Tests for the pure parts of scripts/demo/cut.py: no video is decoded or encoded."""

import json
from pathlib import Path

import pytest
from PIL import Image, ImageFont
from pydantic import ValidationError

from demo.cut import (
    CardLine,
    Segment,
    captioned,
    card,
    load_card,
    load_plan,
    pick,
    segment_frames,
    speed_label,
)

WHITE = (255, 255, 255)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font = ImageFont.load_default(size)
    assert isinstance(font, ImageFont.FreeTypeFont)
    return font


def _rgb(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    pixel = image.getpixel(xy)
    assert isinstance(pixel, tuple)
    return tuple(int(v) for v in pixel)


def test_a_real_time_segment_uses_every_frame() -> None:
    assert segment_frames(Segment(start=1.0, end=2.0, speed=1, caption=""), 15, 1000) == range(
        15, 30
    )


def test_a_sped_up_segment_keeps_every_nth_frame() -> None:
    frames = segment_frames(Segment(start=23.0, end=217.0, speed=12, caption=""), 15, 10_000)
    assert frames[0] == 345
    assert frames[1] == 357
    assert len(frames) == 243  # 194 s at 12x is about 16 s of output


def test_a_segment_past_the_recording_stops_at_its_last_frame() -> None:
    frames = segment_frames(Segment(start=466.0, end=476.9, speed=1, caption=""), 15, 7150)
    assert frames == range(6990, 7150)


def test_the_speed_label_says_it_is_a_live_run() -> None:
    assert speed_label(1) is None
    assert speed_label(12) == "12× speed · live run"


def test_a_caption_keeps_the_frame_size_and_darkens_the_bottom_band() -> None:
    frame = Image.new("RGB", (640, 360), (255, 255, 255))
    out = captioned(frame, "A real property", 1, _font)
    assert out.size == (640, 360)
    assert _rgb(out, (630, 350)) != WHITE
    assert _rgb(out, (630, 10)) == WHITE


def test_a_sped_up_frame_shows_the_red_label_inside_the_top_right_corner() -> None:
    frame = Image.new("RGB", (640, 360), (255, 255, 255))
    out = captioned(frame, "waiting", 12, _font)
    assert _rgb(out, (630, 36)) == WHITE  # the 16 px margin
    red, green, blue = _rgb(out, (620, 50))
    assert red > 200 and green < 80 and blue < 80
    assert _rgb(out, (10, 36)) == WHITE


def test_a_card_is_the_frame_size_with_its_text_centred() -> None:
    lines = [CardLine(text="Button NZ", size=40, bold=True)]
    out = card(lines, (640, 360), _font)
    assert out.size == (640, 360)
    box = out.convert("L").point([255 if v > 128 else 0 for v in range(256)]).getbbox()
    assert box is not None
    left, top, right, bottom = box
    assert abs((left + right) / 2 - 320) <= 2
    assert abs((top + bottom) / 2 - 180) <= 20


def test_load_plan_reads_the_title_and_segments(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "title": [{"text": "Button NZ", "size": 64, "bold": True}],
                "segments": [{"start": 0, "end": 8.5, "speed": 1, "caption": "A site"}],
            }
        )
    )
    plan = load_plan(path)
    assert plan.title == [CardLine(text="Button NZ", size=64, bold=True)]
    assert plan.segments == [Segment(start=0.0, end=8.5, speed=1, caption="A site")]


def test_load_plan_refuses_a_segment_that_ends_before_it_starts(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    segment = {"start": 9, "end": 8, "speed": 1, "caption": ""}
    path.write_text(json.dumps({"title": [], "segments": [segment]}))
    with pytest.raises(ValidationError):
        load_plan(path)


def test_load_card_reads_a_list_of_lines(tmp_path: Path) -> None:
    path = tmp_path / "outro.json"
    path.write_text(json.dumps([{"text": "", "size": 14}]))
    assert load_card(path) == [CardLine(text="", size=14, bold=False)]


def test_the_committed_plan_loads_and_its_segments_run_in_order() -> None:
    plan = load_plan(Path(__file__).resolve().parents[1] / "scripts" / "demo" / "plan.json")
    ends = [s.end for s in plan.segments]
    starts = [s.start for s in plan.segments]
    assert starts[1:] == ends[:-1]


def test_pick_reads_once_and_repeats_an_index_asked_for_twice() -> None:
    assert list(pick(iter("abcdef"), [0, 2, 2, 5])) == ["a", "c", "c", "f"]


def test_pick_stops_when_the_recording_ends() -> None:
    assert list(pick(iter("abc"), [1, 2, 3, 4])) == ["b", "c"]
