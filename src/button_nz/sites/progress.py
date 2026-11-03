"""What a site's build shows while it runs (#152): each step's result, kept
beside the site's files the moment the step has it, for the app to draw.

- **parcels:** the frame everything is drawn in, the title's parcels and
  the LINZ building outlines around them;
- **terrain:** an instant picture of the LiDAR (``terrain_preview``): the
  surface's hillshade tinted by its height, and the range of that height;
- **aerial:** the bbox the site's aerial photo covers;
- **survey:** which concept SAM 3.1 is being asked about, and what it has
  found for each concept so far (``watching``).

``PROGRESS_FILE`` is rewritten whole after each change, and every file is
written beside its name first and then moved into place, so a read in the
middle of a build never sees half of one. Rings are NZTM.
"""

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from shapely import MultiPolygon, Polygon

from button_nz.geo.geometry import BBox, Ring
from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.features import Feature, Mask, features
from button_nz.perception.survey import CONCEPTS, Segment

PROGRESS_FILE = "progress.json"
TERRAIN_PREVIEW = "terrain-preview.png"
TERRAIN_PX_PER_M = 4
LIGHT = (-0.5, 0.5, 0.5**0.5)  # the sun in the north-west, 45° up (east, north, up)
# Low ground to high: teal, green, sand, orange, nearly white.
TINT = np.array(
    [(38, 112, 120), (96, 160, 96), (214, 196, 120), (222, 132, 64), (246, 238, 228)],
    dtype=np.float64,
)

type Shown = dict[str, Any]


def read_progress(directory: Path) -> Shown:
    """What the build in ``directory`` has shown so far (nothing, before it starts)."""
    path = directory / PROGRESS_FILE
    shown: Shown = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    return _empty() | shown


class BuildProgress:
    """A build's progress in ``directory``, each step recorded as it finishes.
    It starts with nothing shown, so a rebuild never shows the last build's."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.shown = _empty()
        directory.mkdir(parents=True, exist_ok=True)
        self._show()

    def parcels(self, frame: BBox, parcels: Sequence[Ring], buildings: Sequence[Ring]) -> None:
        self._show(frame=list(frame), parcels=_rings(parcels), buildings=_rings(buildings))

    def terrain(self, grid: TerrainGrid) -> None:
        surface = grid.dem + grid.ndsm
        write_whole(self.directory / TERRAIN_PREVIEW, terrain_preview(grid))
        low, high = round(float(surface.min()), 2), round(float(surface.max()), 2)
        self._show(terrain={"bbox": list(grid.bbox), "low_m": low, "high_m": high})

    def aerial(self, bbox: BBox) -> None:
        self._show(aerial={"bbox": list(bbox)})

    def watching(self, segment: Segment, grid: TerrainGrid, bbox: BBox, pixel_m: float) -> Segment:
        """``segment``, showing each concept as it is asked and what it found."""

        def watched(image: NDArray[np.uint8], concept: str) -> list[Mask]:
            survey = self.shown["survey"] or {"concepts": list(CONCEPTS), "found": []}
            self._show(survey=survey | {"asking": concept})
            masks = segment(image, concept)
            found = {"concept": concept, "rings": _outlines(features(masks, grid, bbox, pixel_m))}
            done = [*self.shown["survey"]["found"], found]
            self._show(survey=self.shown["survey"] | {"asking": None, "found": done})
            return masks

        return watched

    def _show(self, **changed: Any) -> None:
        self.shown = self.shown | changed
        write_whole(self.directory / PROGRESS_FILE, json.dumps(self.shown).encode())


def terrain_preview(grid: TerrainGrid) -> bytes:
    """The surface (DEM plus nDSM) as a PNG at ``TERRAIN_PX_PER_M``: lit from
    the north-west and tinted from its lowest point to its highest."""
    rows, cols = grid.dem.shape
    per_cell = round(grid.cell_m * TERRAIN_PX_PER_M)
    size = (cols * per_cell, rows * per_cell)
    surface = Image.fromarray((grid.dem + grid.ndsm).astype(np.float32), "F")
    heights = np.asarray(surface.resize(size, Image.Resampling.BILINEAR), dtype=np.float64)
    pixel_m = 1.0 / TERRAIN_PX_PER_M
    down, east = np.gradient(heights, pixel_m)
    normal = np.stack([-east, down, np.ones_like(heights)])  # rows run south: north is -down
    shade = np.clip(np.tensordot(LIGHT, normal, 1) / np.linalg.norm(normal, axis=0), 0.0, 1.0)
    low, high = float(heights.min()), float(heights.max())
    share = (heights - low) / (high - low) if high > low else np.zeros_like(heights)
    tint = np.stack(
        [np.interp(share, np.linspace(0, 1, len(TINT)), TINT[:, band]) for band in range(3)], -1
    )
    lit = tint * (0.45 + 0.75 * shade)[..., None]
    buffer = io.BytesIO()
    Image.fromarray(np.clip(lit, 0, 255).astype(np.uint8), "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _empty() -> Shown:
    return {
        "frame": None,
        "parcels": [],
        "buildings": [],
        "terrain": None,
        "aerial": None,
        "survey": None,
    }


def _rings(rings: Sequence[Ring]) -> list[list[list[float]]]:
    return [[[round(x, 2), round(y, 2)] for x, y in ring] for ring in rings]


def _outlines(found: Sequence[Feature]) -> list[list[list[float]]]:
    """Each feature's outline: one ring for each part, without its holes."""
    parts: list[Polygon] = []
    for feature in found:
        polygon = feature.polygon
        parts += list(polygon.geoms) if isinstance(polygon, MultiPolygon) else [polygon]
    return _rings([tuple((float(x), float(y)) for x, y in part.exterior.coords) for part in parts])


def write_whole(path: Path, body: bytes) -> None:
    """``body`` at ``path``, written beside it first: never seen half written."""
    partial = path.with_name(f"{path.name}.partial")
    partial.write_bytes(body)
    partial.replace(path)
