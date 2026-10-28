"""A survey of what stands on and around the site (plan §6.4): each concept is
segmented on the aerial, checked against the LiDAR, and kept as GeoJSON for a
person to confirm. Raised ground no concept explains is added as unlabelled,
so nothing the LiDAR sees is silently left out.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray
from shapely.geometry import mapping

from button_nz.geo.geometry import BBox
from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.features import Feature, Mask, features, unlabelled

# One short noun phrase each: SAM 3.1 matches a list with nothing.
CONCEPTS = ("building", "shed", "tree", "hedge", "garden bed", "driveway", "path", "car")

type Segment = Callable[[NDArray[np.uint8], str], list[Mask]]


def survey(
    segment: Segment, aerial: NDArray[np.uint8], grid: TerrainGrid, bbox: BBox, pixel_m: float
) -> list[Feature]:
    """Every ``CONCEPTS`` match on ``aerial`` (the crop of ``bbox`` at ``pixel_m``),
    checked against ``grid``, then what stands up that none of them covers."""
    masks = [mask for concept in CONCEPTS for mask in segment(aerial, concept)]
    labelled = features(masks, grid, bbox, pixel_m)
    return labelled + unlabelled(labelled, grid, bbox)


def to_geojson(found: Sequence[Feature], meta: Mapping[str, Any]) -> dict[str, Any]:
    """``found`` as an NZTM FeatureCollection, numbered from 1, with ``meta``
    (e.g. the model and imagery) alongside."""
    return {
        "type": "FeatureCollection",
        **meta,
        "crs": "EPSG:2193",
        "features": [
            {
                "type": "Feature",
                "id": str(number),
                "properties": {
                    "concept": feature.concept,
                    "score": feature.score,
                    "area_m2": feature.area_m2,
                    "max_height_m": feature.max_height_m,
                    "status": feature.status.value,
                    "note": feature.note,
                },
                "geometry": mapping(feature.polygon),
            }
            for number, feature in enumerate(found, 1)
        ],
    }
