"""Tests for scripts/demo/cut.py: its pure parts, and one tiny end-to-end cut."""

import json
from pathlib import Path

import av
import numpy as np
import pytest
from PIL import Image, ImageFont
from pydantic import ValidationError

from demo.cut import (
    BACKGROUND,
    INTRO_CAPTION,
    Beat,
    CardLine,
    Plan,
    Segment,
    captioned,
    card,
    cut,
    fitted,
    headlined,
    indexed_images,
    load_card,
    load_plan,
    pick,
    pick_indexed,
    resampled,
    segment_frame,
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


def test_fitted_letterboxes_a_frame_to_the_output_size() -> None:
    red = Image.new("RGB", (640, 480), (255, 0, 0))
    fit = fitted(red, (1280, 720))
    assert fit.size == (1280, 720)
    assert _rgb(fit, (640, 360)) == (255, 0, 0)
    assert _rgb(fit, (10, 360)) == BACKGROUND  # 4:3 in 16:9: bars at the sides


def test_fitted_leaves_a_frame_of_the_output_size_as_it_is() -> None:
    blue = Image.new("RGB", (1280, 720), (0, 0, 255))
    assert _rgb(fitted(blue, (1280, 720)), (0, 0)) == (0, 0, 255)


def test_resampled_keeps_the_clip_length_at_the_cut_frame_rate() -> None:
    assert resampled(120, 30, 15) == list(range(0, 120, 2))  # 4 s either way
    assert len(resampled(96, 24, 15)) == 60
    assert resampled(4, 15, 30) == [0, 0, 1, 1, 2, 2, 3, 3]


def test_the_intro_caption_says_it_is_not_the_live_run() -> None:
    assert "LiDAR" in INTRO_CAPTION
    assert "not the live run" in INTRO_CAPTION


def _numbered(index: int, size: tuple[int, int]) -> np.ndarray:
    """A black frame with ``index`` in six white-or-black blocks along its top
    edge, which ``_index`` reads back, even darkened under a headline."""
    width, height = size[0] // 8, size[1] // 6
    pixels = np.zeros((size[1], size[0], 3), np.uint8)
    for bit in range(6):
        if index >> bit & 1:
            pixels[:height, bit * width : (bit + 1) * width] = 255
    return pixels


def _index(image: Image.Image) -> int:
    width, height = image.width // 8, image.height // 6
    bits = [_rgb(image, (bit * width + width // 2, height // 2))[0] > 65 for bit in range(6)]
    return sum(1 << bit for bit, on in enumerate(bits) if on)


def _clip(path: Path, size: tuple[int, int], fps: int, frames: int, gop: int | None = None) -> None:
    """``frames`` numbered frames at ``fps``, a keyframe every ``gop`` if given."""
    with av.open(str(path), "w") as sink:
        stream = sink.add_stream("libx264", rate=fps)  # pyright: ignore[reportUnknownMemberType]
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        if gop is not None:
            stream.options = {"g": str(gop)}
        for index in range(frames):
            frame = av.VideoFrame.from_ndarray(_numbered(index, size), format="rgb24")
            sink.mux(stream.encode(frame))  # pyright: ignore[reportUnknownMemberType]
        sink.mux(stream.encode(None))  # pyright: ignore[reportUnknownMemberType]


def _images(path: Path) -> list[Image.Image]:
    with av.open(str(path)) as source:
        return [Image.fromarray(f.to_ndarray(format="rgb24")) for f in source.decode(video=0)]


def _frames(path: Path) -> tuple[int, tuple[int, int]]:
    with av.open(str(path)) as source:
        frames = list(source.decode(video=0))
        return len(frames), (frames[0].width, frames[0].height)


def test_a_cut_plays_the_intro_between_the_title_and_the_live_run(tmp_path: Path) -> None:
    raw, intro, out = tmp_path / "raw.mp4", tmp_path / "intro.mp4", tmp_path / "cut.mp4"
    _clip(raw, (64, 48), 15, 30)
    _clip(intro, (32, 24), 30, 8)  # another size and rate: fitted and resampled
    line = CardLine(text="x", size=8)
    plan = Plan(title=[line], segments=[Segment(start=0, end=1, speed=1, caption="c")])
    cut(raw, out, plan, [line], _font, 15, intro=intro)
    # title 4 s + intro 8 frames at 30 fps as 4 at 15 + 1 s of the run + outro 7 s
    assert _frames(out) == (60 + 4 + 15 + 105, (64, 48))


def test_a_plan_may_open_on_beats_from_anywhere_in_the_run(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    beat = {"start": 900.0, "end": 910.0, "speed": 1, "lines": [{"text": "Why", "size": 40}]}
    segment = {"start": 0.0, "end": 5.0, "speed": 1, "caption": "c"}
    path.write_text(json.dumps({"title": [], "opening": [beat], "segments": [segment]}))
    plan = load_plan(path)
    assert plan.opening[0].start == 900.0  # after every segment: an opening isn't in order
    assert plan.title == []


def test_a_plan_without_an_opening_has_none(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"title": [], "segments": []}))
    assert load_plan(path).opening == []


def test_a_headline_darkens_the_frame_and_keeps_its_size() -> None:
    white = Image.new("RGB", (320, 200), WHITE)
    shown = headlined(white, [CardLine(text="The problem", size=20, bold=True)], 1, _font)
    assert shown.size == (320, 200)
    assert _rgb(shown, (5, 5))[0] < 160  # darkened, so the words read over footage


def test_a_cut_opens_on_its_beats_and_skips_an_empty_title(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw.mp4", tmp_path / "cut.mp4"
    _clip(raw, (64, 48), 15, 30)
    line = CardLine(text="x", size=8)
    plan = Plan.model_validate(
        {
            "title": [],
            "opening": [{"start": 1.0, "end": 2.0, "speed": 1, "lines": [line.model_dump()]}],
            "segments": [{"start": 0.0, "end": 1.0, "speed": 1, "caption": "c"}],
        }
    )
    cut(raw, out, plan, [line], _font, 15)
    # no title, 1 s of opening beat from the run's end, 1 s of the run, outro 7 s
    assert _frames(out) == (15 + 15 + 105, (64, 48))


def test_a_headline_at_the_bottom_leaves_the_middle_of_the_frame_clear() -> None:
    white = Image.new("RGB", (640, 600), WHITE)
    lines = [CardLine(text="The impact", size=12, bold=True)]
    low = headlined(white, lines, 1, _font, at="bottom")
    centred = headlined(white, lines, 1, _font)
    assert _rgb(low, (320, 300)) > _rgb(centred, (320, 300))  # no panel over the middle
    assert _rgb(low, (320, 500))[0] < 60  # the panel is low down


def test_a_beat_without_a_headline_is_refused_when_the_plan_loads() -> None:
    with pytest.raises(ValidationError):
        Beat.model_validate({"start": 1.0, "end": 2.0, "speed": 1, "lines": []})


def test_a_segment_may_carry_a_fact_over_its_footage(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    fact = {"text": "65% of Reefton's properties have room", "size": 30}
    seg = {"start": 0.0, "end": 5.0, "speed": 20, "caption": "Muse writes", "lines": [fact]}
    path.write_text(json.dumps({"title": [], "segments": [seg]}))
    assert load_plan(path).segments[0].lines[0].text.startswith("65%")


def test_a_cut_shows_a_segments_fact_darkened_and_still_captioned(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw.mp4", tmp_path / "cut.mp4"
    _clip(raw, (64, 48), 15, 30)
    line = CardLine(text="x", size=8)
    plan = Plan.model_validate(
        {
            "title": [],
            "segments": [
                {"start": 0.0, "end": 1.0, "speed": 1, "caption": "c", "lines": [line.model_dump()]}
            ],
        }
    )
    cut(raw, out, plan, [line], _font, 15)
    assert _frames(out) == (15 + 105, (64, 48))


def test_a_segment_frame_with_a_fact_is_darkened_captioned_and_labelled_once() -> None:
    white = Image.new("RGB", (640, 400), WHITE)
    fact = CardLine(text="65% have room", size=20)
    seg = Segment(start=0, end=1, speed=20, caption="Muse writes", lines=[fact])
    shown = segment_frame(white, seg, _font)
    assert _rgb(shown, (5, 200))[0] < 160  # darkened under the fact
    assert _rgb(shown, (5, 390))[0] < 80  # the caption band (75% black over white)
    red = _rgb(shown, (600, 30))
    assert red[0] > 150 and red[1] < 120  # the speed label, top right


def test_a_segment_frame_without_a_fact_is_only_captioned() -> None:
    white = Image.new("RGB", (640, 400), WHITE)
    shown = segment_frame(white, Segment(start=0, end=1, speed=1, caption="c"), _font)
    assert _rgb(shown, (5, 200)) == WHITE  # not darkened
    assert _rgb(shown, (5, 390))[0] < 80  # the caption band (75% black over white)


def test_pick_indexed_keeps_the_frames_asked_for_by_their_own_index() -> None:
    frames = iter([(3, "d"), (4, "e"), (5, "f"), (6, "g"), (8, "i")])
    assert list(pick_indexed(frames, [4, 6, 7])) == ["e", "g"]  # 7 isn't there


def test_a_preview_cut_is_half_the_size(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw.mp4", tmp_path / "cut.mp4"
    _clip(raw, (64, 48), 15, 30)
    line = CardLine(text="x", size=8)
    plan = Plan(title=[], segments=[Segment(start=0, end=1, speed=1, caption="c")])
    cut(raw, out, plan, [line], _font, 15, preview=True)
    assert _frames(out) == (15 + 105, (32, 24))


def test_indexed_images_seeks_to_the_keyframe_before_and_numbers_each_frame(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw.mp4"
    _clip(raw, (64, 48), 15, 60, gop=15)  # keyframes at 0, 15, 30 and 45
    with av.open(str(raw)) as source:
        frames = list(indexed_images(source, 3.5, 15))
    assert [index for index, _ in frames] == list(range(45, 60))  # from the keyframe at 3 s
    assert [_index(image) for _, image in frames] == list(range(45, 60))  # the frames they say


def test_a_beat_read_by_seeking_shows_the_frames_of_its_span(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw.mp4", tmp_path / "cut.mp4"
    _clip(raw, (320, 240), 15, 60, gop=15)  # 4 s, so the beat at 3 s seeks mid-file
    line = CardLine(text="x", size=8)
    plan = Plan.model_validate(
        {
            "title": [],
            "opening": [{"start": 3.0, "end": 4.0, "speed": 1, "lines": [line.model_dump()]}],
            "segments": [{"start": 0.0, "end": 1.0, "speed": 1, "caption": "c"}],
        }
    )
    cut(raw, out, plan, [line], _font, 15)
    shown = _images(out)
    assert len(shown) == 15 + 15 + 105
    assert [_index(image) for image in shown[:15]] == list(range(45, 60))  # the beat, darkened
    assert _index(shown[15]) == 0  # then the live run from its start
