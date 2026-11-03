"""Writing a relief clip: animated WebP for the app, MP4 for video editors."""

import io
from pathlib import Path
from typing import Any, cast

import av
import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from button_nz.relief.clip import webp, write_mp4


def _frames(count: int, rows: int = 21, cols: int = 31) -> list[NDArray[np.uint8]]:
    return [np.full((rows, cols, 3), 10 * k, dtype=np.uint8) for k in range(count)]


def test_webp_is_an_endless_loop_of_every_frame() -> None:
    with Image.open(io.BytesIO(webp(_frames(5), fps=10))) as image:
        assert image.format == "WEBP" and cast(Any, image).n_frames == 5
        image.load()  # a frame's duration is read with the frame
        assert image.info["loop"] == 0 and image.info["duration"] == 100
        image.seek(4)
        assert np.asarray(image.convert("RGB"))[10, 10, 0] == pytest.approx(40, abs=3)


def test_mp4_is_h264_with_every_frame(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    write_mp4(_frames(6), fps=12, path=path)
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        assert stream.codec_context.name == "h264"
        decoded = list(container.decode(stream))
    assert len(decoded) == 6
    # H.264's 4:2:0 needs even sides: the odd last row and column are dropped.
    assert (decoded[0].width, decoded[0].height) == (30, 20)


def test_a_clip_needs_frames() -> None:
    with pytest.raises(ValueError, match="no frames"):
        webp([], fps=10)
