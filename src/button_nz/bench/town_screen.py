"""The town screen (#72): how many of a town's residential sections have room
for a real prefab under the granny-flat exemption's siting rules.

    uv run python -m button_nz.bench.town_screen OUT_DIR [--cache var/town-screen]

Fetches BDC's parcels and Residential zones and LINZ's building outlines for
the envelope (Reefton by default), joins the West Coast
LiDAR's DEM and DSM tiles into ``CACHE``, screens every section
(``town.screen``), and writes ``results.jsonl``, ``report.md`` and
``map.png`` to ``OUT_DIR``. One run per directory: an existing
``results.jsonl`` is never overwritten.
"""

import argparse
import math
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from shapely import STRtree

from button_nz.catalogue import Product, load_products
from button_nz.config import ServiceEndpoints
from button_nz.geo.geometry import BBox
from button_nz.geo.terrain import TerrainGrid, read_terrain
from button_nz.town.lidar import mosaic, tall_cells, tile_urls
from button_nz.town.map import draw_map
from button_nz.town.report import report, summarise, write_results
from button_nz.town.screen import EAVE_ALLOWANCE_M, SEPARATION_M, SectionResult, screen_section
from button_nz.town.sources import (
    BDC_ATTRIBUTION,
    BDC_PLANNING_ZONES,
    REEFTON,
    TownData,
    buildings_on,
    fetch,
    reach,
)

LIDAR_TITLE = "West Coast LiDAR 1m DEM and DSM (2020-2024)"
LIDAR_ATTRIBUTION = (
    "Toitū Te Whenua Land Information New Zealand, Aerial Surveys, West Coast Regional Council"
)
LIDAR_CAPTURED = "Captured 2020-05-15 to 2024-07-10"
GRID_MARGIN_M = 10.0  # LiDAR read beyond the sections, for the separation around them


@dataclass(frozen=True)
class Options:
    out_dir: Path
    cache: Path
    envelope: BBox
    place: str


def parse_options(argv: Sequence[str] | None = None) -> Options:
    parser = argparse.ArgumentParser(description="The town screen (#72).")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--cache", type=Path, default=Path("var/town-screen"))
    parser.add_argument(
        "--envelope",
        default=",".join(f"{v:g}" for v in REEFTON),
        help="minx,miny,maxx,maxy in NZTM2000; default: Reefton",
    )
    parser.add_argument("--place", default="Reefton", help="the envelope's name")
    args = parser.parse_args(argv)
    values = [float(v) for v in args.envelope.split(",")]
    if len(values) != 4 or values[0] >= values[2] or values[1] >= values[3]:
        parser.error(f"not an envelope: {args.envelope}")
    envelope = (values[0], values[1], values[2], values[3])
    return Options(args.out_dir, args.cache, envelope, args.place)


def screen_town(
    data: TownData, grid: TerrainGrid, products: Sequence[Product]
) -> list[SectionResult]:
    """Screen every section in ``data`` against its outlines and ``grid``."""
    tree = STRtree(data.buildings)
    results: list[SectionResult] = []
    for section in data.selection.sections:
        reach = section.shape.buffer(SEPARATION_M + 0.1)
        near = [data.buildings[int(i)] for i in tree.query(reach, predicate="intersects")]
        x0, y0, x1, y1 = section.shape.bounds
        margin = SEPARATION_M + 1.0
        tall = tall_cells(grid, (x0 - margin, y0 - margin, x1 + margin, y1 + margin))
        results.append(screen_section(section.parcel_id, section.shape, near, tall, products))
    return results


def lidar_grid(data: TownData, cache: Path) -> tuple[TerrainGrid, BBox, list[str]]:
    """The DEM and nDSM over every section plus ``GRID_MARGIN_M``, joined from
    the LiDAR tiles into ``cache``."""
    x0, y0, x1, y1 = reach(data.selection.sections, GRID_MARGIN_M)
    bbox: BBox = (  # whole metres, on the LiDAR's grid
        float(math.floor(x0)),
        float(math.floor(y0)),
        float(math.ceil(x1)),
        float(math.ceil(y1)),
    )
    dem_urls, dsm_urls = tile_urls(bbox, "dem_1m"), tile_urls(bbox, "dsm_1m")
    dem = mosaic(dem_urls, bbox, cache / "dem.tif")
    dsm = mosaic(dsm_urls, bbox, cache / "dsm.tif")
    return read_terrain(str(dem), str(dsm), bbox, margin_m=0.0), bbox, dem_urls + dsm_urls


def sources(data: TownData, lidar: Sequence[str]) -> list[dict[str, str]]:
    retrieved = f"Retrieved {data.parcels.provenance.retrieved_at:%Y-%m-%d}"
    captured = [int(f["properties"]["capture_source_from"]) for f in data.outlines.features]
    until = [int(f["properties"]["capture_source_to"]) for f in data.outlines.features]
    outlines_dates = (
        f"Captured from aerial photos of {_day(min(captured))} to {_day(max(until))}"
        if captured
        else "No outlines in the envelope"
    )
    return [
        {
            "title": "Buller District Council property parcels",
            "service": data.parcels.provenance.service,
            "licence": "CC-BY-4.0 as recorded in data/demo-site/site.json; "
            "the layer's ArcGIS item states no licence",
            "attribution": BDC_ATTRIBUTION,
            "dates": retrieved,
        },
        {
            "title": "Buller District Council zones (Residential)",
            "service": BDC_PLANNING_ZONES,
            "licence": "no licence stated on the layer's ArcGIS item",
            "attribution": BDC_ATTRIBUTION,
            "dates": retrieved,
        },
        {
            "title": "LINZ NZ Building Outlines",
            "service": data.outlines.provenance.service,
            "licence": "CC-BY-4.0",
            "attribution": "Toitū Te Whenua Land Information New Zealand",
            "dates": outlines_dates,
        },
        {
            "title": LIDAR_TITLE,
            "service": ", ".join(lidar),
            "licence": "CC-BY-4.0",
            "attribution": LIDAR_ATTRIBUTION,
            "dates": LIDAR_CAPTURED,
        },
    ]


def main(argv: Sequence[str] | None = None) -> None:
    options = parse_options(argv)
    commit = _commit()  # before this run writes anything
    options.out_dir.mkdir(parents=True, exist_ok=True)
    log = options.out_dir / "results.jsonl"
    if log.exists():  # one run per directory: no mixed results
        sys.exit(f"{log} exists; write each run to its own directory")
    options.cache.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120) as client:
        data = fetch(ServiceEndpoints.from_env(), client, options.envelope)
    grid, _, lidar = lidar_grid(data, options.cache)
    products = [p for p in load_products() if p.dimensions_labelled]
    results = screen_town(data, grid, products)
    write_results(results, log)
    meta = _meta(commit, options, data, lidar, products)
    (options.out_dir / "report.md").write_text(report(results, meta), encoding="utf-8")
    shapes = {s.parcel_id: s.shape for s in data.selection.sections}
    draw_map(
        results,
        shapes,
        buildings_on(data.selection.sections, data.buildings),
        options.envelope,
        options.out_dir / "map.png",
        title=f"{options.place}: room for a real prefab under the granny-flat "
        f"exemption's siting rules, with {EAVE_ALLOWANCE_M:g} m eaves",
        notes=_map_notes(meta),
    )
    counts = summarise(results)
    print({k: v for k, v in counts.items() if k != "by_product"})


def _meta(
    commit: str,
    options: Options,
    data: TownData,
    lidar: Sequence[str],
    products: Sequence[Product],
) -> dict[str, Any]:
    return {
        "commit": commit,
        "place": options.place,
        "envelope": options.envelope,
        "outside_zone": data.selection.outside_zone,
        "other_intent": data.selection.other_intent,
        "sources": sources(data, lidar),
        "products": {
            p.id: f"{p.supplier} {p.model} ({p.length_m:g} x {p.width_m:g} m)" for p in products
        },
    }


def _map_notes(meta: dict[str, Any]) -> list[str]:
    return [
        f"Code {meta['commit']}. Each parcel alone: 2 m from its boundary and from every "
        "building outline. Not checked: hazards, slope, the district plan, services.",
        "Sources: Buller District Council parcels and zones; LINZ NZ Building Outlines; "
        "West Coast LiDAR 2020-24 (LINZ, Aerial Surveys, West Coast Regional Council).",
    ]


RESULT_INPUTS = ("src", "data", "pyproject.toml", "uv.lock")  # what the results depend on


def _commit() -> str:
    """HEAD, marked if anything the results depend on differs from it. Old
    results deleted to make way for this run's don't count."""

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout

    commit = git("rev-parse", "--short", "HEAD").strip()
    changed = git("status", "--porcelain", "--untracked-files=no", "--", *RESULT_INPUTS).strip()
    return commit + (" with uncommitted changes" if changed else "")


def _day(epoch_ms: int) -> str:
    return f"{datetime.fromtimestamp(epoch_ms / 1000, UTC):%Y-%m-%d}"


if __name__ == "__main__":
    main()
