"""Run the relief tiers cheapest first, publishing each the moment it's ready.

``relief.json`` in the output directory lists every tier from the start
(``pending``), then each as ``running``, and ``ready`` (its files, facts and
seconds) or ``failed`` (why) as soon as it ends, written whole each time. A
reader polling it can show the depth map within a second and the parallax
clip within seconds, while the fly-over is still rendering.

A failed tier doesn't stop the others, which don't depend on it, but the run
raises ``ReliefFailed`` at the end: a failure is reported, never hidden.
"""

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from button_nz.relief import SiteRelief
from button_nz.relief.clip import Frame, webp, write_mp4
from button_nz.relief.depth import depth_map
from button_nz.relief.flyover import FlyoverSettings, render_flyover
from button_nz.relief.parallax import oblique, sway_path

MANIFEST = "relief.json"
PARALLAX_FRAMES, PARALLAX_FPS = 60, 15
PARALLAX_TILT_DEG, PARALLAX_SWAY_DEG = 35.0, 12.0


@dataclass(frozen=True)
class TierOutput:
    files: Mapping[str, str]  # what each file is, and its name in the output directory
    facts: Mapping[str, float]


@dataclass(frozen=True)
class Tier:
    name: str
    make: Callable[[SiteRelief, Path], TierOutput]


class ReliefFailed(RuntimeError):
    """One or more tiers failed; the manifest says which and why."""


def run_relief(relief: SiteRelief, out_dir: Path, tiers: Sequence[Tier]) -> list[dict[str, Any]]:
    """Run ``tiers`` in order into ``out_dir``; the final manifest's tiers."""
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = [{"tier": tier.name, "status": "pending"} for tier in tiers]
    _publish(out_dir, entries)
    for tier, entry in zip(tiers, entries, strict=True):
        entry["status"] = "running"
        _publish(out_dir, entries)
        started = time.perf_counter()
        try:
            output = tier.make(relief, out_dir)
        except Exception as error:  # recorded, then raised once every tier has run
            entry.update(status="failed", error=str(error))
        else:
            entry.update(status="ready", files=dict(output.files), facts=dict(output.facts))
        entry["seconds"] = round(time.perf_counter() - started, 3)
        _publish(out_dir, entries)
    failed = [f"{e['tier']}: {e['error']}" for e in entries if e["status"] == "failed"]
    if failed:
        raise ReliefFailed("; ".join(failed))
    return entries


def _publish(out_dir: Path, entries: list[dict[str, Any]]) -> None:
    partial = out_dir / f"{MANIFEST}.partial"  # a reader never sees half a manifest
    partial.write_text(json.dumps({"tiers": entries}, indent=1), encoding="utf-8")
    partial.replace(out_dir / MANIFEST)


def _depth(relief: SiteRelief, out_dir: Path) -> TierOutput:
    depth = depth_map(relief)
    (out_dir / "depth16.png").write_bytes(depth.png16)
    (out_dir / "depth.png").write_bytes(depth.preview)
    files = {"depth16": "depth16.png", "preview": "depth.png"}
    return TierOutput(files, {"low_m": depth.low_m, "high_m": depth.high_m})


def _parallax(relief: SiteRelief, out_dir: Path) -> TierOutput:
    path = sway_path(PARALLAX_FRAMES, PARALLAX_TILT_DEG, PARALLAX_SWAY_DEG, 0.0)
    frames = [oblique(relief.aerial, relief.heights, relief.pixel_m, t, b) for t, b in path]
    still = oblique(relief.aerial, relief.heights, relief.pixel_m, PARALLAX_TILT_DEG, 0.0)
    Image.fromarray(still, "RGB").save(out_dir / "parallax.png")
    (out_dir / "parallax.webp").write_bytes(webp(frames, PARALLAX_FPS))
    write_mp4(frames, PARALLAX_FPS, out_dir / "parallax.mp4")
    files = {"still": "parallax.png", "clip": "parallax.webp", "video": "parallax.mp4"}
    return TierOutput(files, {"frames": float(len(frames))})


def flyover_tier(settings: FlyoverSettings, blender: str = "blender") -> Tier:
    def make(relief: SiteRelief, out_dir: Path) -> TierOutput:
        paths = render_flyover(relief, out_dir, settings, blender)
        frames = [_rgb(path) for path in paths]
        still = paths[round(len(paths) * 0.4)]  # the tilt done, before the orbit
        Image.open(still).convert("RGB").save(out_dir / "flyover.png")
        (out_dir / "flyover.webp").write_bytes(webp(frames, settings.fps))
        write_mp4(frames, settings.fps, out_dir / "flyover.mp4")
        files = {"still": "flyover.png", "clip": "flyover.webp", "video": "flyover.mp4"}
        return TierOutput(files, {"frames": float(len(frames))})

    return Tier("flyover", make)


def _rgb(path: Path) -> Frame:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


DEPTH = Tier("depth", _depth)
PARALLAX = Tier("parallax", _parallax)
TIERS = (DEPTH, PARALLAX, flyover_tier(FlyoverSettings()))
