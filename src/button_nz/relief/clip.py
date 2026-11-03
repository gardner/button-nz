"""A relief clip's frames as an H.264 MP4: for the app (a muted, looping
``<video>``) and for a video editor. Measured on the demo site, it is 3-5x
smaller than the same frames as an animated WebP, at near-lossless quality.

Its index comes first ("faststart"), so a browser can start playing before
the rest has arrived, and its colours are converted and tagged as BT.709, so
every player reads them the same way.
"""

from collections.abc import Iterable
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np
from numpy.typing import NDArray

type Frame = NDArray[np.uint8]  # rows x cols x RGB

MP4_CRF = "18"  # near lossless, so an editor's re-encode has good footage to start from
BT709 = 1  # ITU-R BT.709's code, as primaries, transfer and matrix alike


def write_mp4(frames: Iterable[Frame], fps: int, path: Path) -> None:
    """``frames`` as H.264, one at a time (4:2:0, which needs even sides: an
    odd last row or column is dropped)."""
    container: Any = av.open(str(path), mode="w", options={"movflags": "faststart"})
    with container:
        stream: Any = None
        for frame in frames:
            if stream is None:
                stream = _stream(container, fps, frame)
            image = np.ascontiguousarray(frame[: stream.height, : stream.width])
            video = av.VideoFrame.from_ndarray(image, format="rgb24")
            converted = video.reformat(format="yuv420p", dst_colorspace="ITU709")
            for packet in stream.encode(converted):
                container.mux(packet)
        if stream is None:
            raise ValueError("a clip with no frames")
        for packet in stream.encode():
            container.mux(packet)


def _stream(container: Any, fps: int, first: Frame) -> Any:
    rows, cols = (side - side % 2 for side in first.shape[:2])
    stream: Any = container.add_stream("libx264", rate=Fraction(fps))
    stream.width, stream.height, stream.pix_fmt = cols, rows, "yuv420p"
    stream.options = {"crf": MP4_CRF}
    context = stream.codec_context
    context.colorspace = context.color_primaries = context.color_trc = BT709
    return stream
