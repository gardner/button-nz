"""Cut the raw live recording into a short demo video.

Real time where a person acts; live waits sped up, with the speed on screen; a
caption per phase. Nothing is staged: every frame between the title and the
closing card is from the one live run in the raw recording.

The title card and the segments come from a plan file (``plan.json`` beside
this script); the closing card comes from ``--outro``, so its claims are the
caller's, taken from real reports. See README.md for both formats.
"""

import argparse
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Self

import av
import numpy as np
from av.container import InputContainer, OutputContainer
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

HERE = Path(__file__).resolve().parent
SANS = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
BACKGROUND = (24, 24, 27)

type Fonts = Callable[[int, bool], ImageFont.FreeTypeFont]
"""A font of a pixel size, bold or not."""


class CardLine(BaseModel):
    """One centred line of a title or closing card; an empty line is a spacer."""

    model_config = ConfigDict(frozen=True)
    text: str
    size: int = Field(gt=0)
    bold: bool = False


class Segment(BaseModel):
    """A span of the raw recording, in its seconds, played at ``speed``."""

    model_config = ConfigDict(frozen=True)
    start: float = Field(ge=0)
    end: float
    speed: int = Field(ge=1)
    caption: str

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.end <= self.start:
            raise ValueError(f"segment ends at {self.end} s, before it starts at {self.start} s")
        return self


class Plan(BaseModel):
    """The title card and the segments, in recording order."""

    title: list[CardLine]
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
    image = Image.new("RGB", size, BACKGROUND)
    draw = ImageDraw.Draw(image)
    heights = [line.size + 18 for line in lines]
    y = (size[1] - sum(heights)) // 2
    for line, height in zip(lines, heights, strict=True):
        font = fonts(line.size, line.bold)
        width = draw.textlength(line.text, font=font)
        draw.text(((size[0] - width) / 2, y), line.text, font=font, fill=(244, 244, 245))
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
    label = speed_label(speed)
    if label is not None:
        label_width = draw.textlength(label, font=font)
        box = (width - label_width - 44, 16, width - 16, 56)
        draw.rounded_rectangle(box, 8, fill=(220, 38, 38, 230))
        draw.text((width - label_width - 30, 22), label, font=font, fill=(255, 255, 255))
    return image


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


def cut(raw: Path, out: Path, plan: Plan, outro: list[CardLine], fonts: Fonts, fps: int) -> None:
    """Write the cut to ``out`` (H.264 MP4), decoding ``raw`` once, in order."""
    with av.open(str(raw)) as source, av.open(str(out), "w") as sink:
        video = source.streams.video[0]
        size = (video.width, video.height)
        mp4 = Mp4(sink, size, fps)
        mp4.write(card(plan.title, size, fonts), 4 * fps)
        plan_shots = shots(plan, fps)
        shown = pick(raw_images(source), [index for index, _ in plan_shots])
        for image, (_, segment) in zip(shown, plan_shots, strict=False):
            mp4.write(captioned(image, segment.caption, segment.speed, fonts))
        mp4.write(card(outro, size, fonts), 7 * fps)
        mp4.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("raw", type=Path, help="the raw recording, e.g. demo-raw.webm")
    parser.add_argument("out", type=Path, help="the cut, an .mp4")
    parser.add_argument("--outro", type=Path, required=True, help="the closing card, JSON")
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--fps", type=int, default=15, help="the raw recording's frame rate")
    parser.add_argument("--sans", type=Path, default=SANS)
    parser.add_argument("--bold", type=Path, default=BOLD)
    args = parser.parse_args(argv)
    fonts = truetype(args.sans, args.bold)
    cut(args.raw, args.out, load_plan(args.plan), load_card(args.outro), fonts, args.fps)


if __name__ == "__main__":
    main()
