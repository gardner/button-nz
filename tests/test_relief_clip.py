"""Writing a relief clip as an MP4, for the app and for video editors."""

from pathlib import Path

import av
import numpy as np
import pytest
from numpy.typing import NDArray

from button_nz.relief.clip import write_mp4


def _frames(count: int, rows: int = 21, cols: int = 31) -> list[NDArray[np.uint8]]:
    return [np.full((rows, cols, 3), 10 * k, dtype=np.uint8) for k in range(count)]


def test_mp4_is_h264_with_every_frame(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    write_mp4(iter(_frames(6)), fps=12, path=path)  # streamed: any iterable of frames
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        assert stream.codec_context.name == "h264"
        decoded = list(container.decode(stream))
    assert len(decoded) == 6
    # H.264's 4:2:0 needs even sides: the odd last row and column are dropped.
    assert (decoded[0].width, decoded[0].height) == (30, 20)


def test_mp4_starts_playing_before_it_has_all_downloaded(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    write_mp4(_frames(3), fps=12, path=path)
    data = path.read_bytes()
    assert data.index(b"moov") < data.index(b"mdat")  # the index first: "faststart"


def test_mp4_says_its_colours_are_bt709(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    write_mp4([np.full((16, 16, 3), (200, 30, 30), dtype=np.uint8)] * 2, fps=12, path=path)
    with av.open(str(path)) as container:
        context = container.streams.video[0].codec_context
        tags = (context.colorspace, context.color_primaries, context.color_trc)
        assert [int(tag) for tag in tags] == [1, 1, 1]  # ITU-R BT.709
        frame = next(container.decode(video=0))
        rgb = frame.to_ndarray(format="rgb24", src_colorspace="ITU709")
    assert np.abs(rgb[8, 8].astype(int) - (200, 30, 30)).max() <= 4


def test_a_clip_needs_frames(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no frames"):
        write_mp4([], fps=10, path=tmp_path / "clip.mp4")
