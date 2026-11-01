"""Tests for button_nz.sites.stac: which LINZ collections cover a site."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from button_nz.geo.tiles import tiles_covering
from button_nz.sites.stac import (
    ELEVATION,
    IMAGERY,
    Catalogues,
    Collection,
    aerial_candidates,
    choose_lidar,
    parse_collection,
)

SITE = (1505926.0, 5336777.0, 1505969.0, 5336822.0)  # the demo site, in one tile of each scale
LIDAR_TILE = tiles_covering(SITE, 10000)[0]
AERIAL_TILE = tiles_covering(SITE, 1000)[0]


def body(title: str, end: str, tiles: list[str], gsd: float = 1.0) -> dict[str, Any]:
    return {
        "title": title,
        "gsd": gsd,
        "license": "CC-BY-4.0",
        "linz:region": "west-coast",
        "providers": [{"name": "Toitū Te Whenua Land Information New Zealand"}],
        "extent": {"temporal": {"interval": [["2020-05-15T12:00:00Z", end]]}},
        "links": [{"rel": "root", "href": "../catalog.json"}]
        + [{"rel": "item", "href": f"./{t}.json"} for t in tiles],
    }


def lidar(survey: str, kind: str, end: str, tiles: list[str]) -> Collection:
    url = f"{ELEVATION}/west-coast/{survey}/{kind}/2193/collection.json"
    return parse_collection(url, body(survey, end, tiles))


def test_a_collection_knows_its_tiles_scale_and_dates() -> None:
    found = lidar("west-coast_2020-2022", "dem_1m", "2024-07-10T12:00:00Z", [LIDAR_TILE])
    assert found.scale == 10000
    assert found.region == "west-coast"
    assert found.end == "2024-07-10T12:00:00Z"
    assert found.providers == ("Toitū Te Whenua Land Information New Zealand",)
    assert found.tiles_for(SITE) == [
        f"{ELEVATION}/west-coast/west-coast_2020-2022/dem_1m/2193/{LIDAR_TILE}.tiff"
    ]


def test_a_site_reaching_a_tile_the_collection_lacks_is_not_covered() -> None:
    found = lidar("west-coast_2020-2022", "dem_1m", "2024-07-10T12:00:00Z", [LIDAR_TILE])
    wider = (SITE[0], SITE[1], SITE[2] + 5000.0, SITE[3])
    assert found.tiles_for(wider) is None


def test_half_metre_scale_tiles_have_six_digits() -> None:
    tile = tiles_covering(SITE, 500)[0]
    found = parse_collection(f"{IMAGERY}/x/rgb/2193/collection.json", body("x", "2025", [tile]))
    assert found.scale == 500 and found.tiles_for(SITE) is not None


def test_tiles_at_two_scales_are_refused() -> None:
    with pytest.raises(ValueError, match="scales"):
        parse_collection("x", body("x", "2024-01-01", [LIDAR_TILE, AERIAL_TILE]))


def test_the_newest_survey_with_both_dem_and_dsm_is_chosen() -> None:
    index = [
        lidar("old_2010", "dem_1m", "2010-01-01T00:00:00Z", [LIDAR_TILE]),
        lidar("old_2010", "dsm_1m", "2010-01-01T00:00:00Z", [LIDAR_TILE]),
        lidar("new_2024", "dem_1m", "2024-01-01T00:00:00Z", [LIDAR_TILE]),
        lidar("new_2024", "dsm_1m", "2024-01-01T00:00:00Z", [LIDAR_TILE]),
        lidar("dem_only_2025", "dem_1m", "2025-01-01T00:00:00Z", [LIDAR_TILE]),
    ]
    chosen = choose_lidar(index, SITE)
    assert chosen is not None
    dem, dsm = chosen
    assert "new_2024/dem_1m" in dem.url and "new_2024/dsm_1m" in dsm.url


def test_no_lidar_covering_the_site_is_none() -> None:
    index = [lidar("x_2024", "dem_1m", "2024-01-01T00:00:00Z", ["BS21_10000_0101"])]
    assert choose_lidar(index, SITE) is None


def test_aerials_rank_fine_enough_first_then_newest() -> None:
    links = [
        "./west-coast/buller_2024-2025_0.075m/rgb/2193/collection.json",
        "./west-coast/west-coast_2024-2026_0.2m/rgb/2193/collection.json",
        "./west-coast/buller_2016_0.1m/rgb/2193/collection.json",
        "./west-coast/west-coast_1978_0.3m/rgb/2193/collection.json",  # too old
        "./west-coast/west-coast_2022_0.5m/rgb/2193/collection.json",  # too coarse
        "./canterbury/christchurch_2025_0.075m/rgb/2193/collection.json",  # another region
    ]
    assert aerial_candidates(links, "west-coast") == [
        f"{IMAGERY}/west-coast/buller_2024-2025_0.075m/rgb/2193/collection.json",
        f"{IMAGERY}/west-coast/buller_2016_0.1m/rgb/2193/collection.json",
        f"{IMAGERY}/west-coast/west-coast_2024-2026_0.2m/rgb/2193/collection.json",
    ]


def catalogues(tmp_path: Path, seen: list[str]) -> Catalogues:
    elevation_links = [
        "./west-coast/wc_2022/dem_1m/2193/collection.json",
        "./west-coast/wc_2022/dsm_1m/2193/collection.json",
        "./west-coast/wc_2022/dem_hillshade/2193/collection.json",  # not indexed
    ]
    imagery_links = [
        "./west-coast/buller_2025_0.075m/rgb/2193/collection.json",
        "./west-coast/west-coast_2025_0.2m/rgb/2193/collection.json",
    ]
    pages: dict[str, Any] = {
        f"{ELEVATION}/catalog.json": {
            "links": [{"rel": "child", "href": h} for h in elevation_links]
        },
        f"{IMAGERY}/catalog.json": {"links": [{"rel": "child", "href": h} for h in imagery_links]},
        f"{ELEVATION}/west-coast/wc_2022/dem_1m/2193/collection.json": body(
            "dem", "2022-01-01", [LIDAR_TILE]
        ),
        f"{ELEVATION}/west-coast/wc_2022/dsm_1m/2193/collection.json": body(
            "dsm", "2022-01-01", [LIDAR_TILE]
        ),
        f"{IMAGERY}/west-coast/buller_2025_0.075m/rgb/2193/collection.json": body(
            "Buller 0.075m", "2025-01-01", ["BS21_1000_0101"], 0.075
        ),
        f"{IMAGERY}/west-coast/west-coast_2025_0.2m/rgb/2193/collection.json": body(
            "West Coast 0.2m", "2025-01-01", [AERIAL_TILE], 0.2
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=json.dumps(pages[str(request.url)]))

    return Catalogues(httpx.Client(transport=httpx.MockTransport(handler)), tmp_path)


def test_the_lidar_index_is_built_once_and_cached(tmp_path: Path) -> None:
    seen: list[str] = []
    first = catalogues(tmp_path, seen).lidar_index()
    assert len(first) == 2 and len(seen) == 3  # the catalogue and two collections
    again = catalogues(tmp_path, seen).lidar_index()
    assert again == first and len(seen) == 3
    assert choose_lidar(again, SITE) is not None


def test_the_best_aerial_that_covers_the_site_is_used(tmp_path: Path) -> None:
    found = catalogues(tmp_path, []).aerial_for("west-coast", SITE)
    assert found is not None
    collection, tiles = found
    assert collection.title == "West Coast 0.2m"  # the 7.5 cm one doesn't reach the site
    assert tiles == [f"{IMAGERY}/west-coast/west-coast_2025_0.2m/rgb/2193/{AERIAL_TILE}.tiff"]
