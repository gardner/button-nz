"""What the LiDAR says stands where, on a site's 1 m grid.

- ``height_above``: how tall something stands: the 90th percentile of the
  nDSM (surface minus ground) over the cells whose centres it covers, so a
  chimney or an aerial doesn't set a roof's height.
- ``median_ground``: the ground under it: the median DEM over the same cells.
- ``canopy``: what stands over ``CANOPY_M`` outside the buildings (trees,
  hedges), as simplified polygons, each with its height.

None where no cell's centre is covered, or where the grid doesn't cover the
whole of the geometry: a part isn't measured as the whole. Nothing is guessed.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np
import rasterio.features  # pyright: ignore[reportMissingTypeStubs]
import rasterio.transform  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray
from shapely import Polygon, box, union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from button_nz.geo.terrain import TerrainGrid

CANOPY_M = 2.0  # as the survey's evidence height
MIN_CANOPY_M2 = 4.0  # smaller is a speck: a post, a bird, noise
SIMPLIFY_M = 0.5  # half a cell: cell steps smoothed, shapes kept
OUTLINE_SLACK_M = 1.0  # LINZ outlines sit up to ~1 m off the LiDAR's roofs

features: Any = rasterio.features  # untyped, as in geo.terrain
transforms: Any = rasterio.transform


def _transform(grid: TerrainGrid) -> Any:
    left, _, _, top = grid.bbox
    return transforms.from_origin(left, top, grid.cell_m, grid.cell_m)


def _covered(grid: TerrainGrid, geometry: BaseGeometry) -> NDArray[np.bool_]:
    """The cells whose centres ``geometry`` covers; none unless the grid covers
    all of ``geometry``."""
    if geometry.is_empty or not box(*grid.bbox).covers(geometry):
        return np.zeros(grid.dem.shape, dtype=bool)
    outside: NDArray[np.bool_] = features.geometry_mask(
        [geometry], out_shape=grid.dem.shape, transform=_transform(grid), all_touched=False
    )
    return ~outside


def height_above(grid: TerrainGrid, geometry: BaseGeometry) -> float | None:
    cells = grid.ndsm[_covered(grid, geometry)]
    return None if cells.size == 0 else float(np.percentile(cells, 90))


def median_ground(grid: TerrainGrid, geometry: BaseGeometry) -> float | None:
    cells = grid.dem[_covered(grid, geometry)]
    return None if cells.size == 0 else float(np.median(cells))


def canopy(grid: TerrainGrid, buildings: Sequence[BaseGeometry]) -> list[tuple[Polygon, float]]:
    """What stands over ``CANOPY_M`` and isn't a building, with its height. The
    buildings are grown by ``OUTLINE_SLACK_M`` first, so an outline a little off
    its roof leaves no roof-high strip of "canopy" beside the wall."""
    tall = (grid.ndsm > CANOPY_M).astype(np.uint8)
    shapes = features.shapes(tall, mask=tall.astype(bool), transform=_transform(grid))
    built = union_all(list(buildings)).buffer(OUTLINE_SLACK_M) if buildings else Polygon()
    found: list[tuple[Polygon, float]] = []
    for raw, _ in shapes:
        polygon = shape(raw).difference(built).simplify(SIMPLIFY_M)
        for part in getattr(polygon, "geoms", [polygon]):
            if not isinstance(part, Polygon) or part.area < MIN_CANOPY_M2:
                continue
            height = height_above(grid, part)
            if height is not None:
                found.append((part, height))
    return found
