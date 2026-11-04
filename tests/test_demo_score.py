"""Tests for scripts/demo/score.py: the fades, and one tiny end-to-end score."""

import wave
from pathlib import Path

import av
import numpy as np
import pytest

from demo.score import HEADROOM, faded, headroomed, score

RATE = 32_000


def test_faded_ramps_in_and_out_and_leaves_the_middle() -> None:
    ones = np.ones((2, RATE * 4), np.float32)
    out = faded(ones, RATE, fade_in_s=0.5, fade_out_s=1.0)
    assert out.shape == ones.shape
    assert out[:, 0].tolist() == [0.0, 0.0]
    assert out[:, -1].tolist() == [0.0, 0.0]
    assert np.allclose(out[:, RATE * 2], 1.0)  # the middle is untouched
    assert 0.4 < out[0, RATE // 4] < 0.6  # half way into the fade-in


def _video(path: Path, seconds: int, fps: int = 15) -> None:
    with av.open(str(path), "w") as sink:
        stream = sink.add_stream("libx264", rate=fps)  # pyright: ignore[reportUnknownMemberType]
        stream.width, stream.height = 64, 48
        stream.pix_fmt = "yuv420p"
        for _ in range(seconds * fps):
            frame = av.VideoFrame.from_ndarray(np.zeros((48, 64, 3), np.uint8), format="rgb24")
            sink.mux(stream.encode(frame))  # pyright: ignore[reportUnknownMemberType]
        sink.mux(stream.encode(None))  # pyright: ignore[reportUnknownMemberType]


def _music(path: Path, seconds: float) -> None:
    t = np.arange(int(RATE * seconds)) / RATE
    tone = (0.3 * 32767 * np.sin(2 * np.pi * 220 * t)).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(np.stack([tone, tone]).T.tobytes())


def test_score_puts_the_music_under_the_video_cut_to_its_length(tmp_path: Path) -> None:
    video, music, out = tmp_path / "cut.mp4", tmp_path / "music.wav", tmp_path / "scored.mp4"
    _video(video, 2)
    _music(music, 3.5)
    score(video, music, out)
    with av.open(str(out)) as scored:
        assert len(scored.streams.video) == 1 and len(scored.streams.audio) == 1
        frames = sum(1 for _ in scored.decode(video=0))
    with av.open(str(out)) as scored:
        samples = sum(f.samples for f in scored.decode(audio=0))
        rate = scored.streams.audio[0].rate
    assert frames == 30  # the video's frames, untouched
    assert abs(samples / rate - 2.0) < 0.1  # the music, cut to the video's 2 s


def test_score_refuses_music_shorter_than_the_video(tmp_path: Path) -> None:
    video, music = tmp_path / "cut.mp4", tmp_path / "music.wav"
    _video(video, 2)
    _music(music, 1.0)
    with pytest.raises(ValueError, match="shorter than the video"):
        score(video, music, tmp_path / "scored.mp4")


def test_headroomed_brings_a_loud_peak_down_to_the_headroom() -> None:
    loud = np.array([[0.5, -1.0, 0.25]], np.float32)
    out = headroomed(loud)
    assert np.isclose(np.abs(out).max(), HEADROOM)
    assert np.allclose(out / out[0, 1], loud / loud[0, 1])  # one gain for all of it


def test_headroomed_leaves_quiet_music_as_it_is() -> None:
    quiet = np.array([[0.1, -0.2]], np.float32)
    assert np.array_equal(headroomed(quiet), quiet)
