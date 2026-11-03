"""A relief clip's frames as an H.264 MP4: for the app (a muted, looping
``<video>``) and for a video editor. Measured on the demo site, it is 3-5x
smaller than the same frames as an animated WebP, at near-lossless quality."""

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
import numpy as np
from numpy.typing import NDArray

type Frame = NDArray[np.uint8]  # rows x cols x RGB

MP4_CRF = "18"  # near lossless, so an editor's re-encode has good footage to start from


def write_mp4(frames: Sequence[Frame], fps: int, path: Path) -> None:
    """``frames`` as H.264 (4:2:0, which needs even sides: an odd last row or
    column is dropped)."""
    if not frames:
        raise ValueError("a clip with no frames")
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
