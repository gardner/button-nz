"""Tier 2: the aerial draped on the DSM in Blender, flown over.

The camera is tilted towards the site's centre, as far from it as fits the
site in the frame from straight overhead, and orbits it once at an even
speed (``camera.flyover_path``), so the clip loops without a jump.
Blender (``blender_worker/relief_flyover.py``) renders one PNG per pose, on
the GPU: a run that leaves any frame missing raises, never a short clip.
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from button_nz.blender_worker.run import BlenderError, run_script
from button_nz.relief import SiteRelief
from button_nz.relief.camera import fitting_distance, flyover_path
from button_nz.relief.parallax import BACKGROUND, WALL_SHADE

SCRIPT = Path(__file__).parents[1] / "blender_worker" / "relief_flyover.py"
SENSOR_MM = 36.0
# Blender's inputs and the frames it renders, beside the clip: an editor's,
# about 100 MB a site, which the app doesn't keep (``api.relief``).
INPUT_DIR, FRAMES_DIR = "flyover-input", "flyover-frames"
WORK_DIRS = (INPUT_DIR, FRAMES_DIR)


@dataclass(frozen=True)
class FlyoverSettings:
    frames: int = 288  # one turn in 12 s: 1.25 degrees a frame
    fps: int = 24
    width: int = 1280
    height: int = 720
    tilt_deg: float = 40.0
    bearing_deg: float = 0.0  # the way it looks at the first frame: 0 is north
    lens_mm: float = 35.0
    samples: int = 8  # unlit, so only edges need them


def render_flyover(
    relief: SiteRelief,
    out_dir: Path,
    settings: FlyoverSettings,
    blender: str = "blender",
    timeout_s: float = 900.0,
) -> list[Path]:
    """Render the fly-over's frames into ``out_dir/flyover-frames``, in order."""
    inputs, frames_dir = out_dir / INPUT_DIR, out_dir / FRAMES_DIR
    for directory in (inputs, frames_dir):
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
    spec = flyover_spec(relief, settings, inputs, frames_dir)
    (inputs / "flyover.json").write_text(json.dumps(spec), encoding="utf-8")
    run_script(SCRIPT, [str(inputs / "flyover.json")], blender, timeout_s)
    frames = [frames_dir / f"frame_{index:04d}.png" for index in range(settings.frames)]
    missing = [frame.name for frame in frames if not frame.is_file()]
    if missing:
        raise BlenderError(f"Blender did not render {len(missing)} frame(s), from {missing[0]}")
    return frames


def flyover_spec(
    relief: SiteRelief, settings: FlyoverSettings, inputs: Path, frames_dir: Path
) -> dict[str, object]:
    """What ``relief_flyover.py`` renders, in a frame centred on the site,
    with its inputs written to ``inputs``."""
    rows, cols = relief.surface.shape
    half_w, half_h = cols * relief.cell_m / 2, rows * relief.cell_m / 2
    np.save(inputs / "surface.npy", relief.surface.astype(np.float32))
    Image.fromarray(relief.aerial, "RGB").save(inputs / "aerial.png")
    distance = fitting_distance(
        2 * half_w, 2 * half_h, settings.width / settings.height, settings.lens_mm, SENSOR_MM
    )
    target = (0.0, 0.0, relief.centre_m)
    poses = flyover_path(settings.frames, target, distance, settings.tilt_deg, settings.bearing_deg)
    return {
        "surface": str(inputs / "surface.npy"),
        "aerial": str(inputs / "aerial.png"),
        "cell_m": relief.cell_m,
        "bbox": [-half_w, -half_h, half_w, half_h],
        "poses": [{"location": p.location, "rotation": p.rotation} for p in poses],
        "frames_dir": str(frames_dir),
        "width": settings.width,
        "height": settings.height,
        "lens_mm": settings.lens_mm,
        "sensor_mm": SENSOR_MM,
        "clip_end_m": 4 * distance,
        "samples": settings.samples,
        "background": list(BACKGROUND),
        # Blender shades light, not the photo's sRGB values: 2.2 is sRGB's gamma.
        "wall_shade": WALL_SHADE**2.2,
    }
