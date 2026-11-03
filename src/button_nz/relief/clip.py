"""A relief clip's frames as an animated WebP (the app shows it as an image)
and as an H.264 MP4 (for a video editor)."""

import io
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np
from numpy.typing import NDArray
from PIL import Image

type Frame = NDArray[np.uint8]  # rows x cols x RGB

WEBP_QUALITY = 80
MP4_CRF = "18"  # visually lossless, so an editor's re-encode has good footage to start from


def webp(frames: Sequence[Frame], fps: float) -> bytes:
    """``frames`` as a WebP that loops for ever."""
    first, *rest = _images(frames)
    buffer = io.BytesIO()
    first.save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=rest,
        duration=round(1000 / fps),
        loop=0,
        quality=WEBP_QUALITY,
    )
    return buffer.getvalue()


def write_mp4(frames: Sequence[Frame], fps: int, path: Path) -> None:
    """``frames`` as H.264 (4:2:0, which needs even sides: an odd last row or
    column is dropped)."""
    _images(frames)  # none is an error
    rows, cols = (side - side % 2 for side in frames[0].shape[:2])
    container: Any = av.open(str(path), mode="w")
    with container:
        stream: Any = container.add_stream("libx264", rate=Fraction(fps))
        stream.width, stream.height, stream.pix_fmt = cols, rows, "yuv420p"
        stream.options = {"crf": MP4_CRF}
        for frame in frames:
            image = np.ascontiguousarray(frame[:rows, :cols])
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _images(frames: Sequence[Frame]) -> list[Image.Image]:
    if not frames:
        raise ValueError("a clip with no frames")
    return [Image.fromarray(frame, "RGB") for frame in frames]
