"""Put music under the cut demo video: the video stream copied as it is, the
music cut to its length, faded in and out, and encoded as AAC.

The music must be at least as long as the video: it is cut, never looped or
padded. See README.md for how the published video's music was made.
"""

import argparse
from pathlib import Path

import av
import numpy as np
from av.audio.stream import AudioStream
from av.container import OutputContainer
from av.video.stream import VideoStream

FADE_IN_S = 0.5
FADE_OUT_S = 4.0
HEADROOM = 10 ** (-1 / 20)  # a peak of -1 dBFS, so the AAC encoder doesn't clip


def faded(samples: np.ndarray, rate: int, fade_in_s: float, fade_out_s: float) -> np.ndarray:
    """``samples`` (channels × frames) with a linear fade in and out."""
    gain = np.ones(samples.shape[1], np.float32)
    length = samples.shape[1]
    fade_in, fade_out = min(round(fade_in_s * rate), length), min(round(fade_out_s * rate), length)
    gain[:fade_in] = np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    gain[-fade_out:] = np.minimum(gain[-fade_out:], np.linspace(1.0, 0.0, fade_out))
    return (samples * gain).astype(np.float32)


def headroomed(samples: np.ndarray) -> np.ndarray:
    """``samples`` scaled down, all by one gain, so its peak is ``HEADROOM``;
    quieter music is left as it is."""
    peak = float(np.abs(samples).max())
    return samples if peak <= HEADROOM else (samples * (HEADROOM / peak)).astype(np.float32)


def read_music(path: Path) -> tuple[np.ndarray, int]:
    """The music's samples (channels × frames, float32 in [-1, 1]) and rate."""
    with av.open(str(path)) as source:
        stream = source.streams.audio[0]
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=stream.rate)
        chunks = [
            out.to_ndarray() for frame in source.decode(stream) for out in resampler.resample(frame)
        ]
        return np.concatenate(chunks, axis=1), stream.rate


def video_seconds(path: Path) -> float:
    with av.open(str(path)) as source:
        video = source.streams.video[0]
        frames = sum(1 for packet in source.demux(video) if packet.size)
        return frames / float(video.average_rate)


def score(video: Path, music: Path, out: Path) -> None:
    """Write ``out``: ``video`` unchanged, ``music`` under it at its length."""
    seconds = video_seconds(video)
    samples, rate = read_music(music)
    if samples.shape[1] / rate < seconds:
        raise ValueError(
            f"{music} is {samples.shape[1] / rate:.1f} s, shorter than the video's {seconds:.1f} s"
        )
    samples = faded(samples[:, : round(seconds * rate)], rate, FADE_IN_S, FADE_OUT_S)
    samples = headroomed(samples)
    with av.open(str(video)) as source, av.open(str(out), "w") as sink:
        src: VideoStream = source.streams.video[0]
        copy = sink.add_stream_from_template(src)  # pyright: ignore[reportUnknownMemberType]
        audio: AudioStream = sink.add_stream("aac", rate=rate, layout="stereo")  # pyright: ignore[reportUnknownMemberType]
        audio.bit_rate = 192_000
        for packet in source.demux(src):
            if packet.dts is None:
                continue
            packet.stream = copy
            sink.mux(packet)  # pyright: ignore[reportUnknownMemberType]
        _encode(sink, audio, samples, rate)


def _encode(sink: OutputContainer, audio: AudioStream, samples: np.ndarray, rate: int) -> None:
    frame = av.AudioFrame.from_ndarray(
        np.ascontiguousarray(samples), format="fltp", layout="stereo"
    )
    frame.sample_rate = rate
    sink.mux(audio.encode(frame))  # pyright: ignore[reportUnknownMemberType]
    sink.mux(audio.encode(None))  # pyright: ignore[reportUnknownMemberType]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("video", type=Path, help="the cut, an .mp4 from cut.py")
    parser.add_argument("music", type=Path, help="the music, e.g. a .wav, at least as long")
    parser.add_argument("out", type=Path, help="the scored video, an .mp4")
    args = parser.parse_args(argv)
    score(args.video, args.music, args.out)


if __name__ == "__main__":
    main()
