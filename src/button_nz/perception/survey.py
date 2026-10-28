"""A survey of what stands on and around the site (plan §6.4): each concept is
segmented on the aerial, checked against the LiDAR, and kept as GeoJSON for a
person to confirm. Raised ground no concept explains is added as unlabelled,
so nothing the LiDAR sees is silently left out. For the demo site:

    uv run --env-file .env python -m button_nz.perception.survey [DATA]

writes ``DATA/survey.geojson`` (default ``var``), where the API reads it. A new
survey replaces the old one, and the owner's decisions start afresh.
"""

import argparse
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from shapely import Polygon, union_all
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from button_nz.geo.geometry import BBox
from button_nz.geo.terrain import TerrainGrid
from button_nz.perception.features import (
    STRUCTURES,
    Feature,
    Mask,
    features,
    unlabelled,
)

SURVEY_FILE = "survey.geojson"
SAME_IOU = 0.8  # two outlines this alike are one thing
PIXEL_M = 0.125  # the aerial is 7.5 cm: 12.5 cm keeps sheds and paths several pixels wide
# One short noun phrase each: SAM 3.1 matches a list with nothing.
CONCEPTS = ("building", "shed", "tree", "hedge", "garden bed", "driveway", "path", "car")

type Segment = Callable[[NDArray[np.uint8], str], list[Mask]]


def survey(
    segment: Segment,
    aerial: NDArray[np.uint8],
    grid: TerrainGrid,
    bbox: BBox,
    pixel_m: float,
    within: BaseGeometry | None = None,
) -> list[Feature]:
    """Every ``CONCEPTS`` match on ``aerial`` (the crop of ``bbox`` at ``pixel_m``),
    checked against ``grid``, then what stands up that none of them covers; only
    what touches ``within`` (the owner's title), if given. Everything is found
    first, so a labelled neighbour's shed never shows up as unlabelled."""
    masks = [mask for concept in CONCEPTS for mask in segment(aerial, concept)]
    labelled = _distinct(features(masks, grid, bbox, pixel_m))
    found = labelled + unlabelled(labelled, grid, bbox)
    return found if within is None else [f for f in found if f.polygon.intersects(within)]


def _distinct(labelled: Sequence[Feature]) -> list[Feature]:
    """One feature per thing: where two concepts' outlines mostly coincide (a shed
    is also a "building"), the likelier label is kept and the other named."""
    kept: dict[int, Feature] = {}  # by position in ``labelled``, to keep its order
    for n in sorted(range(len(labelled)), key=lambda n: -(labelled[n].score or 0.0)):
        feature = labelled[n]
        same = next(
            (k for k, f in kept.items() if _iou(f.polygon, feature.polygon) >= SAME_IOU), None
        )
        if same is None:
            kept[n] = feature
        else:
            kept[same] = _merged(kept[same], feature)
    return [kept[n] for n in sorted(kept)]


def _merged(kept: Feature, other: Feature) -> Feature:
    """``kept``, noting that ``other`` matched it too. If only one of them is a
    structure, the score mustn't settle whether it's a building: the structure
    is kept, with its LiDAR evidence, so the owner must decide it."""
    if other.concept == kept.concept or f"as a {other.concept}" in kept.note:
        return kept
    if other.concept in STRUCTURES and kept.concept not in STRUCTURES:
        kept, other = other, kept
    return replace(kept, note=f"{kept.note} Also matched as a {other.concept}.")


def _iou(a: BaseGeometry, b: BaseGeometry) -> float:
    union = a.union(b).area
    return a.intersection(b).area / union if union else 0.0


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


def write_survey(data: Path, found: Sequence[Feature], meta: Mapping[str, Any]) -> Path:
    """``found`` as ``data/survey.geojson``, written whole and then moved into place,
    so the API never reads half a survey."""
    data.mkdir(parents=True, exist_ok=True)
    path = data / SURVEY_FILE
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(to_geojson(found, meta), indent=1), encoding="utf-8")
    os.replace(partial, path)
    return path


def main(argv: Sequence[str] | None = None) -> None:
    # Imported here: the demo site and the API client are only needed to run it.
    from button_nz.agent.demo import demo_aerial, demo_site
    from button_nz.demo_site import load_demo_site
    from button_nz.perception.sam import SAM_MODEL, Segmenter

    parser = argparse.ArgumentParser(description="Survey the demo site with SAM 3.1.")
    parser.add_argument("data", type=Path, nargs="?", default=Path("var"))
    args = parser.parse_args(argv)
    try:
        segmenter = Segmenter.from_env()
    except KeyError as error:
        raise SystemExit(str(error.args[0])) from None
    site = demo_site()
    grid = site.context.terrain
    title = union_all([Polygon(ring) for ring in site.context.parcels])
    aerial = demo_aerial(site, PIXEL_M)
    found = survey(segmenter.masks, aerial, grid, grid.bbox, PIXEL_M, within=title)
    source = load_demo_site().rasters["aerial"]
    meta = {
        "model": SAM_MODEL,
        "concepts": list(CONCEPTS),
        "aerial": {
            "title": source.title,
            "captured": [source.capture.start.isoformat(), source.capture.end.isoformat()],
        },
        "lidar": grid.sources,
        "surveyed_at": datetime.now(UTC).isoformat(),
    }
    path = write_survey(args.data, found, meta)
    counts = ", ".join(f"{n} {s}" for s, n in _by_status(found).items())
    print(f"{len(found)} features ({counts}) in {path}")


def _by_status(found: Sequence[Feature]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in found:
        counts[feature.status.value] = counts.get(feature.status.value, 0) + 1
    return counts


if __name__ == "__main__":
    main()
