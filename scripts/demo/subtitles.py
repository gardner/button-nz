"""The demo cut's words as subtitles: what each part shows or says, timed by
the frames it spans, as SubRip (SRT), for a voice-over or to ship alongside."""

from collections.abc import Sequence
from typing import Protocol

type Cue = tuple[int, int, str]
"""Words shown or spoken from one frame of the cut up to another."""


class Line(Protocol):
    """What subtitles need of a card's line: its words."""

    @property
    def text(self) -> str: ...


def speed_label(speed: int) -> str | None:
    return f"{speed}× speed · live run" if speed > 1 else None


def srt(cues: Sequence[Cue], fps: int) -> str:
    """``cues`` as SubRip subtitles, each timed by its frames at ``fps``."""

    def stamp(frame: int) -> str:
        ms = round(frame * 1000 / fps)
        return (
            f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        )

    return "\n".join(
        f"{n}\n{stamp(a)} --> {stamp(b)}\n{text}\n" for n, (a, b, text) in enumerate(cues, 1)
    )


def spoken(words: str, speed: int) -> str:
    """``words``, then the speed label if the part is sped up: the subtitles
    say every word the cut shows, the label included."""
    return "\n".join(filter(None, [words, speed_label(speed)]))


def words(lines: Sequence[Line]) -> str:
    """A card's or headline's words, one line each, without the spacers."""
    return "\n".join(line.text for line in lines if line.text)
