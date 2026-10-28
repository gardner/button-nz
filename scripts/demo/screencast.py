"""Capture a page as video through Chrome's CDP screencast.

Playwright's own video recorder needs an ffmpeg build this OS lacks, so this
asks Chrome for JPEG frames instead, and keeps each one's arrival time.
``Screencast.encode`` resamples them to a constant rate and encodes them with
the ffmpeg build Playwright caches, which reads files, not pipes, and only
encodes VP9. Named marks are written beside the video, so the cut can find
each phase of the run.
"""

import base64
import json
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict, cast

from playwright.sync_api import BrowserContext, Page

PLAYWRIGHT_CACHE = Path.home() / ".cache" / "ms-playwright"

type Mark = tuple[float, str]


class MarksDocument(TypedDict):
    """The ``<video>.marks.json`` file: the run's length and its named moments."""

    seconds: float
    marks: list[Mark]


def find_chromium(cache: Path = PLAYWRIGHT_CACHE) -> Path:
    """The newest headless shell Playwright has installed under ``cache``."""
    shells = cache.glob("chromium_headless_shell-*/*/chrome-headless-shell")
    newest = sorted(shells, key=lambda p: int(p.parts[-3].rsplit("-", 1)[1]))
    if not newest:
        raise FileNotFoundError(
            f"no chrome-headless-shell under {cache}; "
            "run `uv run playwright install chromium-headless-shell`"
        )
    return newest[-1]


def find_ffmpeg(cache: Path = PLAYWRIGHT_CACHE) -> Path:
    """The newest ffmpeg build Playwright has installed under ``cache``: found
    before a take, so a missing encoder can't lose a paid run's footage."""
    builds = [p for p in cache.glob("ffmpeg-*/ffmpeg-linux") if p.is_file()]
    newest = sorted(builds, key=lambda p: int(p.parent.name.rsplit("-", 1)[1]))
    if not newest:
        raise FileNotFoundError(
            f"no ffmpeg-linux under {cache}; run `uv run playwright install ffmpeg`"
        )
    return newest[-1]


def tick_frames(stamps: Sequence[float], end: float, fps: int) -> list[int]:
    """For each tick of a constant ``fps`` clock up to ``end``, the frame on screen.

    That is the latest frame captured at or before the tick, or the first frame
    for ticks before any arrived. Chrome sends frames only when the page
    changes, so a still page repeats its last frame.
    """
    if not stamps:
        return []
    shown: list[int] = []
    index = tick = 0
    while tick / fps < end:
        while index + 1 < len(stamps) and stamps[index + 1] <= tick / fps:
            index += 1
        shown.append(index)
        tick += 1
    return shown


def frame_event(event: object) -> tuple[bytes, int]:
    """The JPEG and session id of a CDP ``Page.screencastFrame`` event."""
    if not isinstance(event, dict):
        raise TypeError(f"screencast frame event is not an object: {event!r}")
    fields = cast(dict[str, object], event)
    data, session = fields.get("data"), fields.get("sessionId")
    if not isinstance(data, str) or not isinstance(session, int):
        raise TypeError(f"screencast frame event lacks data or sessionId: {sorted(fields)}")
    return base64.b64decode(data), session


def encode_command(ffmpeg: Path, stream: Path, fps: int, out: Path) -> list[str]:
    """ffmpeg arguments that encode a concatenated-JPEG file to VP9 WebM."""
    return [
        str(ffmpeg), "-y", "-loglevel", "warning",
        "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", str(stream),
        "-c:v", "libvpx-vp9", "-b:v", "3M", "-pix_fmt", "yuv420p", str(out),
    ]  # fmt: skip


def marks_document(seconds: float, marks: list[Mark]) -> MarksDocument:
    return {"seconds": round(seconds, 1), "marks": marks}


class Screencast:
    """Records ``page`` from construction until ``encode``."""

    def __init__(self, context: BrowserContext, page: Page, ffmpeg: Path) -> None:
        self.frames: list[tuple[float, bytes]] = []
        self.marks: list[Mark] = []
        self.ffmpeg = ffmpeg
        self.cdp = context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self._send("Page.startScreencast", {"format": "jpeg", "quality": 85, "everyNthFrame": 1})
        self.start = time.time()

    def _send(self, method: str, params: dict[str, object]) -> None:
        # Playwright types CDP params and results as a bare ``Dict``; none are read here.
        self.cdp.send(method, params)  # pyright: ignore[reportUnknownMemberType]

    def _frame(self, event: object) -> None:
        jpeg, session = frame_event(event)
        self.frames.append((time.time() - self.start, jpeg))
        self._send("Page.screencastFrameAck", {"sessionId": session})

    def mark(self, label: str) -> None:
        """A named moment, so a long wait can be cut or sped up, and labelled as such."""
        self.marks.append((round(time.time() - self.start, 1), label))
        print(f"[{self.marks[-1][0]:7.1f}s] {label}", flush=True)

    def encode(self, path: Path, fps: int = 15) -> None:
        """Stop capturing; write ``path`` (VP9 WebM) and ``path.marks.json``."""
        self._send("Page.stopScreencast", {})
        end = time.time() - self.start
        stream = path.with_name(path.name + ".mjpeg")  # this ffmpeg reads files, not pipes
        with stream.open("wb") as out:
            for index in tick_frames([t for t, _ in self.frames], end, fps):
                out.write(self.frames[index][1])
        subprocess.run(encode_command(self.ffmpeg, stream, fps, path), check=True)
        stream.unlink()
        marks = path.with_name(path.name + ".marks.json")
        marks.write_text(json.dumps(marks_document(end, self.marks), indent=1))
