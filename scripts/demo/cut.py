"""Cut the raw live recording into a short demo video.

Real time where a person acts; live waits sped up, with the speed on screen; a
caption per phase. Nothing is staged: every frame between the title and the
closing card is from the one live run in the raw recording, except an optional
intro (``--intro``): the site's relief fly-over, captioned as not the live run.

The title card and the segments come from a plan file (``plan.json`` beside
this script); the closing card comes from ``--outro``, so its claims are the
caller's, taken from real reports. See README.md for both formats.
"""

import argparse
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Literal, Self

import av
import numpy as np
from av.container import InputContainer, OutputContainer
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

HERE = Path(__file__).resolve().parent
SANS = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
BACKGROUND = (24, 24, 27)
INTRO_CAPTION = "The site in 3D: its LINZ aerial photo on its own LiDAR (not the live run)"

type Fonts = Callable[[int, bool], ImageFont.FreeTypeFont]
"""A font of a pixel size, bold or not."""

type Place = Literal["centre", "bottom"]
"""Where a beat's headline stands: over the middle, or low, clear of the result."""


class CardLine(BaseModel):
    """One centred line of a title or closing card; an empty line is a spacer."""

    model_config = ConfigDict(frozen=True)
    text: str
    size: int = Field(gt=0)
    bold: bool = False


class Segment(BaseModel):
    """A span of the raw recording, in its seconds, played at ``speed``; with
    ``lines``, a fact over it (a long wait, darkened), still captioned."""

    model_config = ConfigDict(frozen=True)
    start: float = Field(ge=0)
    end: float
    speed: int = Field(ge=1)
    caption: str
    lines: list[CardLine] = []

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"segment ends at {self.end} s, before it starts at {self.start} s")
        return self


class Beat(BaseModel):
    """An opening shot: a span of the raw recording, from anywhere in it,
    darkened under a headline, the why before the how."""

    model_config = ConfigDict(frozen=True)
    start: float = Field(ge=0)
    end: float
    speed: int = Field(ge=1)
    lines: list[CardLine] = Field(min_length=1)
    at: Place = "centre"

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"beat ends at {self.end} s, before it starts at {self.start} s")
        return self


class Plan(BaseModel):
    """The opening beats, the title card (none if empty), and the segments,
    in recording order."""

    title: list[CardLine]
    opening: list[Beat] = []
    segments: list[Segment]

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        for before, after in zip(self.segments, self.segments[1:], strict=False):
            if after.start < before.end:
                raise ValueError(f"segment at {after.start} s overlaps the one before it")
        return self


def load_plan(path: Path) -> Plan:
    return Plan.model_validate_json(path.read_bytes())


def load_card(path: Path) -> list[CardLine]:
    return TypeAdapter(list[CardLine]).validate_json(path.read_bytes())


def truetype(sans: Path, bold: Path) -> Fonts:
    def font(size: int, is_bold: bool) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(bold if is_bold else sans), size)

    return font


def segment_frames(segment: Segment, fps: int, limit: int | None = None) -> range:
    """Indices of the raw frames a segment shows: every ``speed``-th one."""
    stop = round(segment.end * fps)
    if limit is not None:
        stop = min(stop, limit)
    return range(round(segment.start * fps), stop, segment.speed)


def speed_label(speed: int) -> str | None:
    return f"{speed}× speed · live run" if speed > 1 else None


def card(lines: list[CardLine], size: tuple[int, int], fonts: Fonts) -> Image.Image:
    return _centred(
        Image.new("RGB", size, BACKGROUND), lines, fonts, _top(size[1], lines, "centre")
    )


def headlined(
    image: Image.Image, lines: list[CardLine], speed: int, fonts: Fonts, at: Place = "centre"
) -> Image.Image:
    """The frame darkened, its headline centred over it, and, if sped up, the
    red speed label."""
    shown = Image.blend(image.convert("RGB"), Image.new("RGB", image.size, BACKGROUND), 0.6)
    top = _top(image.height, lines, at)
    return labelled(_centred(_panel(shown, lines, fonts, top), lines, fonts, top), speed, fonts)


def _top(height: int, lines: list[CardLine], at: Place) -> int:
    """Where the first of ``lines`` stands: centred, or 56 px clear of the bottom."""
    tall = sum(line.size + 18 for line in lines)
    return (height - tall) // 2 if at == "centre" else height - tall - 56 - 32


def _panel(image: Image.Image, lines: list[CardLine], fonts: Fonts, top: int) -> Image.Image:
    """A dark rounded panel where ``_centred`` will write ``lines``, so they
    read over busy footage."""
    draw = ImageDraw.Draw(image, "RGBA")
    widest = max(draw.textlength(line.text, font=fonts(line.size, line.bold)) for line in lines)
    tall = sum(line.size + 18 for line in lines)
    x, y = (image.width - widest) / 2 - 40, top - 32
    box = (x, y, image.width - x, y + tall + 64)
    draw.rounded_rectangle(box, 24, fill=(*BACKGROUND, 235))
    return image


def _centred(image: Image.Image, lines: list[CardLine], fonts: Fonts, top: int) -> Image.Image:
    """``lines`` centred across ``image``, the first standing at ``top``."""
    draw = ImageDraw.Draw(image)
    heights = [line.size + 18 for line in lines]
    y = top
    for line, height in zip(lines, heights, strict=True):
        font = fonts(line.size, line.bold)
        width = draw.textlength(line.text, font=font)
        draw.text(((image.width - width) / 2, y), line.text, font=font, fill=(244, 244, 245))
        y += height
    return image


def captioned(image: Image.Image, caption: str, speed: int, fonts: Fonts) -> Image.Image:
    """The frame with its caption along the bottom and, if sped up, a red speed label."""
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    font = fonts(24, False)
    draw.rectangle((0, height - 64, width, height), fill=(0, 0, 0, 190))
    draw.text((24, height - 48), caption, font=font, fill=(255, 255, 255))
    return labelled(image, speed, fonts)


def labelled(image: Image.Image, speed: int, fonts: Fonts) -> Image.Image:
    """The frame with, if sped up, the red speed label in its top-right corner."""
    label = speed_label(speed)
    if label is None:
        return image
    draw = ImageDraw.Draw(image, "RGBA")
    font = fonts(24, False)
    label_width = draw.textlength(label, font=font)
    box = (image.width - label_width - 44, 16, image.width - 16, 56)
    draw.rounded_rectangle(box, 8, fill=(220, 38, 38, 230))
    draw.text((image.width - label_width - 30, 22), label, font=font, fill=(255, 255, 255))
    return image


def fitted(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """The image scaled to fit ``size`` whole, centred on the background."""
    if image.size == size:
        return image.convert("RGB")
    scale = min(size[0] / image.width, size[1] / image.height)
    scaled = image.convert("RGB").resize(
        (round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS
    )
    framed = Image.new("RGB", size, BACKGROUND)
    framed.paste(scaled, ((size[0] - scaled.width) // 2, (size[1] - scaled.height) // 2))
    return framed


def resampled(frames: int, fps_in: float, fps_out: int) -> list[int]:
    """Indices of a clip's frames to show at ``fps_out``, keeping its length."""
    shown = round(frames * fps_out / fps_in)
    return [int(i * fps_in / fps_out) for i in range(shown)]


def shots(plan: Plan, fps: int) -> list[tuple[int, Segment]]:
    """Each raw frame index to show, with its segment, in output order."""
    return [(index, segment) for segment in plan.segments for index in segment_frames(segment, fps)]


def pick[T](items: Iterable[T], indices: Iterable[int]) -> Iterator[T]:
    """The items at non-decreasing ``indices``, reading ``items`` once.

    Stops at the end of ``items``, so a plan may run past the recording's end.
    """
    source = enumerate(items)
    step = next(source, None)
    for index in indices:
        while step is not None and step[0] < index:
            step = next(source, None)
        if step is None:
            return
        yield step[1]


def raw_images(source: InputContainer) -> Iterator[Image.Image]:
    for frame in source.decode(video=0):
        yield Image.fromarray(frame.to_ndarray(format="rgb24"))


class Mp4:
    """An H.264 stream at ``fps`` in an open output container."""

    def __init__(self, sink: OutputContainer, size: tuple[int, int], fps: int) -> None:
        self.sink = sink
        # PyAV's stubs leave add_stream's **kwargs and Packet's parameter untyped.
        self.stream = sink.add_stream("libx264", rate=fps)  # pyright: ignore[reportUnknownMemberType]
        self.stream.width, self.stream.height = size
        self.stream.pix_fmt = "yuv420p"
        self.stream.options = {"crf": "20", "preset": "medium"}

    def write(self, image: Image.Image, times: int = 1) -> None:
        frame = av.VideoFrame.from_ndarray(np.asarray(image.convert("RGB")), format="rgb24")
        for _ in range(times):
            self._mux(frame)

    def flush(self) -> None:
        self._mux(None)

    def _mux(self, frame: av.VideoFrame | None) -> None:
        self.sink.mux(self.stream.encode(frame))  # pyright: ignore[reportUnknownMemberType]


def write_beat(mp4: Mp4, raw: Path, beat: Beat, fonts: Fonts, fps: int) -> None:
    """An opening beat: its span of ``raw``, read on its own, headlined."""
    span = Segment(start=beat.start, end=beat.end, speed=beat.speed, caption="")
    with av.open(str(raw)) as source:
        for image in pick(raw_images(source), segment_frames(span, fps)):
            mp4.write(headlined(image, beat.lines, beat.speed, fonts, beat.at))


def write_intro(mp4: Mp4, intro: Path, size: tuple[int, int], fonts: Fonts, fps: int) -> None:
    """The intro clip, fitted to ``size`` at ``fps``, every frame captioned."""
    with av.open(str(intro)) as source:
        rate = source.streams.video[0].average_rate
        images = list(raw_images(source))
    for index in resampled(len(images), float(rate), fps):
        mp4.write(captioned(fitted(images[index], size), INTRO_CAPTION, 1, fonts))


def cut(
    raw: Path,
    out: Path,
    plan: Plan,
    outro: list[CardLine],
    fonts: Fonts,
    fps: int,
    intro: Path | None = None,
) -> None:
    """Write the cut to ``out`` (H.264 MP4), decoding ``raw`` once, in order,
    for the segments, and once more, on its own, for each opening beat."""
    with av.open(str(raw)) as source, av.open(str(out), "w") as sink:
        video = source.streams.video[0]
        size = (video.width, video.height)
        mp4 = Mp4(sink, size, fps)
        for beat in plan.opening:
            write_beat(mp4, raw, beat, fonts, fps)
        if plan.title:
            mp4.write(card(plan.title, size, fonts), 4 * fps)
        if intro is not None:
            write_intro(mp4, intro, size, fonts, fps)
        plan_shots = shots(plan, fps)
        shown = pick(raw_images(source), [index for index, _ in plan_shots])
        for image, (_, segment) in zip(shown, plan_shots, strict=False):
            shown = headlined(image, segment.lines, 1, fonts) if segment.lines else image
            mp4.write(captioned(shown, segment.caption, segment.speed, fonts))
        mp4.write(card(outro, size, fonts), 7 * fps)
        mp4.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("raw", type=Path, help="the raw recording, e.g. demo-raw.webm")
    parser.add_argument("out", type=Path, help="the cut, an .mp4")
    parser.add_argument("--outro", type=Path, required=True, help="the closing card, JSON")
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument(
        "--intro", type=Path, help="a clip after the title, e.g. the relief fly-over's MP4"
    )
    parser.add_argument("--fps", type=int, default=15, help="the raw recording's frame rate")
    parser.add_argument("--sans", type=Path, default=SANS)
    parser.add_argument("--bold", type=Path, default=BOLD)
    args = parser.parse_args(argv)
    fonts = truetype(args.sans, args.bold)
    plan, outro = load_plan(args.plan), load_card(args.outro)
    cut(args.raw, args.out, plan, outro, fonts, args.fps, intro=args.intro)


if __name__ == "__main__":
    main()
