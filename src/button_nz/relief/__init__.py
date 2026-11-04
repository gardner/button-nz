"""Relief views: a site's aerial photo made to look 3D by its own LiDAR.

The aerial looks straight down and the 1 m DSM is on the same NZTM grid, so
the photo's depth is measured, not estimated. Each tier turns the two into a
view, cheapest first, so a caller can show the first while the next renders
(``relief.run``):

0. ``depth``: the heights on the photo's own pixels, as a depth map;
1. ``parallax``: the photo lifted onto its heights and seen at a tilt;
2. ``flyover``: the photo draped on the DSM in Blender, flown round.

Nothing is invented: every height is LiDAR and every colour the photo. A
photo taken straight down never saw a wall, so a wall is the colour of the
roof edge above it, stretched down and shaded darker so it reads as a wall.
"""

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, eq=False)
class SiteRelief:
    """The aerial (rows x cols x RGB, north up, ``pixel_m`` per pixel) over the
    same ground as ``surface``: the DSM's heights above the site's datum, one
    per ``cell_m`` cell, row 0 the north edge."""

    aerial: NDArray[np.uint8]
    surface: NDArray[np.float64]
    cell_m: float
    pixel_m: float

    def __post_init__(self) -> None:
        rows, cols = self.surface.shape
        scale = self.cell_m / self.pixel_m
        expected = (round(rows * scale), round(cols * scale), 3)
        if self.aerial.shape != expected:
            raise ValueError(f"the aerial is {self.aerial.shape}, not {expected}: the grid's")

    @cached_property
    def centre_m(self) -> float:
        """The surface's median height: what the views centre on."""
        return float(np.median(self.surface))

    @cached_property
    def heights(self) -> NDArray[np.float64]:
        """The surface on the aerial's pixels: bilinear between cell centres,
        and the edge cell's height in the half cell past the last centre."""
        rows, cols = self.aerial.shape[:2]
        return on_pixels(self.surface, (rows, cols))


def on_pixels(surface: NDArray[np.float64], shape: tuple[int, int]) -> NDArray[np.float64]:
    """``surface`` resampled to ``shape`` pixels over the same ground."""
    rows, cols = surface.shape
    y = _centres(shape[0], rows)
    x = _centres(shape[1], cols)
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    y1, x1 = np.minimum(y0 + 1, rows - 1), np.minimum(x0 + 1, cols - 1)
    fy, fx = (y - y0)[:, None], (x - x0)[None, :]
    top = surface[np.ix_(y0, x0)] * (1 - fx) + surface[np.ix_(y0, x1)] * fx
    bottom = surface[np.ix_(y1, x0)] * (1 - fx) + surface[np.ix_(y1, x1)] * fx
    return top * (1 - fy) + bottom * fy


def _centres(pixels: int, cells: int) -> NDArray[np.float64]:
    """Each pixel centre's place in cell units (0 at the first cell's centre),
    clamped to the first and last centres."""
    return np.clip((np.arange(pixels) + 0.5) * cells / pixels - 0.5, 0.0, cells - 1.0)
