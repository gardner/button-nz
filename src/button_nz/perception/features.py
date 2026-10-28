"""Site features from segmentation masks, georeferenced and cross-checked
against the LiDAR (plan §6.4).

A mask labels pixels of the aerial crop with a concept ("shed", "tree",
"driveway"). Each becomes an NZTM polygon, and its label is checked against
the nDSM, the measured height above ground: a shed should stand up, a driveway
shouldn't. Agreement is reported, never assumed. A conflict (or a raised area
nothing labelled) goes to a person to confirm, since the aerial and the LiDAR
were captured years apart and either may be out of date.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
import shapely
from numpy.typing import NDArray
from rasterio import features as _features  # pyright: ignore[reportMissingTypeStubs]
from rasterio import transform as _transform  # pyright: ignore[reportMissingTypeStubs]
from shapely import MultiPolygon, Polygon, box, union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from button_nz.geo.geometry import BBox, covers
from button_nz.geo.terrain import TerrainGrid

# rasterio has no type stubs: typed Any, and everything from it converted at once.
rio_features: Any = _features
rio_transform: Any = _transform

STRUCTURES = frozenset({"building", "house", "shed", "garage", "carport"})
VEGETATION = frozenset({"tree", "hedge", "shrub"})
GROUND = frozenset({"driveway", "path", "lawn", "garden bed", "patio"})
TRANSIENT = frozenset({"vehicle", "car", "trailer"})
STRUCTURE_HEIGHT_M = 2.0  # nDSM above this counts as standing up
VEGETATION_HEIGHT_M = 1.5
GROUND_HEIGHT_M = 0.5  # nDSM below this counts as open ground
MIN_STRUCTURE_SHARE = 0.5
MIN_GROUND_SHARE = 0.8
MIN_UNLABELLED_M2 = 4.0


class Status(StrEnum):
    AGREES = "agrees"  # the label and the LiDAR concur
    CONFLICT = "conflict"  # they don't: a person decides
    TRANSIENT = "transient"  # e.g. a parked car: not part of the site
    UNCHECKED = "unchecked"  # no rule for the concept, or too small for 1 m LiDAR
    UNLABELLED = "unlabelled"  # raised ground no mask covers


@dataclass(frozen=True)
class Mask:
    concept: str
    score: float
    pixels: NDArray[np.bool_]  # rows x columns of the aerial crop, north row first


@dataclass(frozen=True)
class Feature:
    concept: str
    score: float | None
    polygon: Polygon | MultiPolygon  # NZTM
    area_m2: float
    max_height_m: float | None  # nDSM over the cells inside, if any
    status: Status
    note: str


def features(masks: Sequence[Mask], grid: TerrainGrid, bbox: BBox, pixel_m: float) -> list[Feature]:
    """Each mask on the crop of ``bbox`` (``pixel_m`` per pixel) as a checked feature."""
    if not covers(grid.bbox, bbox):
        raise ValueError(f"the LiDAR grid {grid.bbox} doesn't cover the crop {bbox}")
    west, south, east, north = bbox
    expected = (round((north - south) / pixel_m), round((east - west) / pixel_m))
    transform = rio_transform.from_origin(west, north, pixel_m, pixel_m)
    found: list[Feature] = []
    for mask in masks:
        if mask.pixels.shape != expected:
            raise ValueError(
                f"a {mask.concept} mask is {mask.pixels.shape}, not the crop's {expected}"
            )
        polygon = _polygons(mask.pixels, transform)
        if polygon.is_empty:
            continue
        found.append(_checked(mask.concept, mask.score, polygon, _heights(polygon, grid)))
    return found


def unlabelled(labelled: Sequence[Feature], grid: TerrainGrid, bbox: BBox) -> list[Feature]:
    """What the LiDAR shows standing up inside the crop ``bbox`` that no labelled
    feature covers: each uncovered piece of at least ``MIN_UNLABELLED_M2``, so a
    lean-to joined to a labelled shed is still reported, without the shed.
    Labelled areas are grown by a LiDAR cell first: cells overshoot a roof edge
    by up to half a cell, and the photo and the LiDAR may be a little apart."""
    if not covers(grid.bbox, bbox):
        raise ValueError(f"the LiDAR grid {grid.bbox} doesn't cover the crop {bbox}")
    raised = grid.ndsm >= STRUCTURE_HEIGHT_M
    left, _, _, top = grid.bbox
    transform = rio_transform.from_origin(left, top, grid.cell_m, grid.cell_m)
    shapes = rio_features.shapes(raised.astype(np.uint8), mask=raised, transform=transform)
    standing = union_all([shape(geometry) for geometry, _ in shapes]).intersection(box(*bbox))
    covered = union_all([f.polygon for f in labelled]).buffer(grid.cell_m)
    left_over = _area(standing.difference(covered))
    pieces = list(left_over.geoms) if isinstance(left_over, MultiPolygon) else [left_over]
    found: list[Feature] = []
    for piece in pieces:
        if piece.is_empty or piece.area < MIN_UNLABELLED_M2 - 1e-6:
            continue
        heights = _heights(piece, grid)
        tallest = float(heights.max()) if heights.size else None
        note = f"The LiDAR shows {piece.area:.0f} m² standing up here; no mask labels it."
        found.append(
            Feature("unlabelled", None, piece, piece.area, tallest, Status.UNLABELLED, note)
        )
    return found


def _polygons(pixels: NDArray[np.bool_], transform: Any) -> Polygon | MultiPolygon:
    pieces = [
        shape(geometry)
        for geometry, _ in rio_features.shapes(
            pixels.astype(np.uint8), mask=pixels, transform=transform
        )
    ]
    return _area(union_all(pieces))


def _area(geometry: BaseGeometry) -> Polygon | MultiPolygon:
    return geometry if isinstance(geometry, Polygon | MultiPolygon) else Polygon()


def _heights(polygon: Polygon | MultiPolygon, grid: TerrainGrid) -> NDArray[np.float64]:
    """The nDSM at every cell centre inside ``polygon``."""
    rows, cols = grid.dem.shape
    xs = grid.bbox[0] + (np.arange(cols, dtype=np.float64) + 0.5) * grid.cell_m
    ys = grid.bbox[3] - (np.arange(rows, dtype=np.float64) + 0.5) * grid.cell_m
    x, y = np.meshgrid(xs, ys)
    return grid.ndsm[shapely.contains_xy(polygon, x, y)]


def _checked(
    concept: str, score: float, polygon: Polygon | MultiPolygon, heights: NDArray[np.float64]
) -> Feature:
    area = polygon.area
    if concept in TRANSIENT:
        return Feature(
            concept, score, polygon, area, None, Status.TRANSIENT, "Not part of the site."
        )
    if heights.size == 0:
        note = "Smaller than the 1 m LiDAR cells: no height to check it against."
        return Feature(concept, score, polygon, area, None, Status.UNCHECKED, note)
    status, note = _verdict(concept, heights)
    return Feature(concept, score, polygon, area, float(heights.max()), status, note)


def _verdict(concept: str, heights: NDArray[np.float64]) -> tuple[Status, str]:
    standing = float(np.mean(heights >= STRUCTURE_HEIGHT_M))
    if concept in STRUCTURES:
        agrees = standing >= MIN_STRUCTURE_SHARE
        return _status(
            agrees
        ), f"The LiDAR shows {standing:.0%} of it over {STRUCTURE_HEIGHT_M:g} m."
    if concept in VEGETATION:
        tallest = float(heights.max())
        agrees = tallest >= VEGETATION_HEIGHT_M
        return _status(agrees), f"The LiDAR shows it up to {tallest:.1f} m tall."
    if concept in GROUND:
        open_ground = float(np.mean(heights < GROUND_HEIGHT_M))
        note = f"The LiDAR shows {open_ground:.0%} of it under {GROUND_HEIGHT_M:g} m."
        return _status(open_ground >= MIN_GROUND_SHARE), note
    return Status.UNCHECKED, f"No LiDAR rule for a {concept}."


def _status(agrees: bool) -> Status:
    return Status.AGREES if agrees else Status.CONFLICT
