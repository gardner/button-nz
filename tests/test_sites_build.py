"""Tests for button_nz.sites.build: a site from an address, out of open data,
with every network read faked."""

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import numpy as np
import pytest
import rasterio  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray

from button_nz.demo_site import load_demo_site
from button_nz.geo.arcgis import FeatureLayer
from button_nz.geo.geometry import BBox
from button_nz.geo.tiles import tiles_covering
from button_nz.perception.features import Mask
from button_nz.sites.build import (
    MAX_SIDE_M,
    NoLidar,
    SiteError,
    Sources,
    build_site,
    build_title_site,
    title_site_name,
)
from button_nz.sites.stac import ELEVATION, IMAGERY, Catalogues, Collection

rio: Any = rasterio
# Two parcels on title 354613 inside one 1:10,000 tile, and a third on another title.
X0, Y0 = 1505930.0, 5336780.0
A = [[X0, Y0], [X0 + 20, Y0], [X0 + 20, Y0 + 30], [X0, Y0 + 30], [X0, Y0]]
B = [[X0 + 20, Y0], [X0 + 40, Y0], [X0 + 40, Y0 + 30], [X0 + 20, Y0 + 30], [X0 + 20, Y0]]
POINT = [X0 + 10.0, Y0 + 15.0]


def parcel(pid: int, ring: list[list[float]], titles: str | None) -> dict[str, Any]:
    props = {"id": pid, "appellation": f"Lot {pid}", "titles": titles, "survey_area": 600}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


C = [[X0 + 40, Y0], [X0 + 60, Y0], [X0 + 60, Y0 + 30], [X0 + 40, Y0 + 30], [X0 + 40, Y0]]
PARCELS = [parcel(2, B, "354613"), parcel(1, A, "354613"), parcel(3, C, "3546130")]
# The road reserve along the title's south side: a road parcel, with no title.
ROAD = {
    "type": "Feature",
    "properties": {"id": 50, "appellation": None, "titles": None, "parcel_intent": "Road"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [X0 - 20, Y0 - 15],
                [X0 + 80, Y0 - 15],
                [X0 + 80, Y0],
                [X0 - 20, Y0],
                [X0 - 20, Y0 - 15],
            ]
        ],
    },
}


def layers(parcels: list[dict[str, Any]], point: list[float] = POINT) -> dict[str, FeatureLayer]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if "Addresses_Roads" in url.path:  # Test Street's centreline, south of the title
            props = {"road_id": 99, "full_road_name": "Test Street"}
            line = {"type": "LineString", "coordinates": [[X0 - 20, Y0 - 7.5], [X0 + 80, Y0 - 7.5]]}
            found = [{"type": "Feature", "properties": props, "geometry": line}]
        elif "Addresses" in url.path:
            address = {"address_id": 7, "full_address": "1 Test Street, Reefton", "road_id": 99}
            found = [
                {
                    "type": "Feature",
                    "properties": address,
                    "geometry": {"type": "Point", "coordinates": point},
                }
            ]
        elif "Parcels" in url.path and q.get("geometryType") == "esriGeometryEnvelope":
            found = [*parcels, ROAD]  # around the title: its parcels and the road beside it
        elif "Parcels" in url.path and q.get("geometryType") == "esriGeometryPoint":
            found = parcels  # the builder keeps those that cover the point
        elif "Parcels" in url.path and q.get("where", "").startswith("id = "):
            wanted = int(q["where"].removeprefix("id = "))
            found = [p for p in parcels if p["properties"]["id"] == wanted]
        elif "Parcels" in url.path:
            titles = re.findall(r"'%(.+?)%'", q["where"])  # LIKE clauses, OR'd
            found = [p for p in parcels if any(t in str(p["properties"]["titles"]) for t in titles)]
        else:  # one courtyard building beside the title, its hole kept
            outer = [
                [X0 + 50, Y0],
                [X0 + 70, Y0],
                [X0 + 70, Y0 + 20],
                [X0 + 50, Y0 + 20],
                [X0 + 50, Y0],
            ]
            hole = [
                [X0 + 55, Y0 + 5],
                [X0 + 65, Y0 + 5],
                [X0 + 65, Y0 + 15],
                [X0 + 55, Y0 + 15],
                [X0 + 55, Y0 + 5],
            ]
            props = {"building_id": 9, "capture_source_name": "NZ Aerial Imagery"}
            geometry = {"type": "Polygon", "coordinates": [outer, hole]}
            found = [{"type": "Feature", "properties": props, "geometry": geometry}]
        return httpx.Response(
            200, text=json.dumps({"type": "FeatureCollection", "features": found})
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return {
        name: FeatureLayer(
            f"https://example.test/{name}/FeatureServer/0", "CC-BY-4.0", "LINZ", client
        )
        for name in (
            "LINZ_NZ_Addresses",
            "LINZ_NZ_Addresses_Roads",
            "LINZ_NZ_Primary_Parcels",
            "LINZ_NZ_Building_Outlines",
        )
    }


def collection(url: str, title: str, scale: int, bbox: BBox, gsd: float = 1.0) -> Collection:
    return Collection(
        url=url,
        title=title,
        region="west-coast",
        gsd_m=gsd,
        start="2020-05-15T12:00:00Z",
        end="2024-07-10T12:00:00Z",
        licence="CC-BY-4.0",
        providers=("Toitū Te Whenua Land Information New Zealand",),
        scale=scale,
        tiles=tuple(tiles_covering(bbox, scale)),
    )


class FakeCatalogues(Catalogues):
    def __init__(self, lidar: bool = True, gappy_newer: bool = False) -> None:
        self.lidar, self.gappy_newer = lidar, gappy_newer

    def lidar_index(self) -> list[Collection]:
        if not self.lidar:
            return []
        reach = (X0 - 100, Y0 - 100, X0 + 140, Y0 + 130)
        surveys = ["wc_2022", "wc_2025_gappy"] if self.gappy_newer else ["wc_2022"]
        found: list[Collection] = []
        for survey in surveys:
            base = f"{ELEVATION}/west-coast/{survey}"
            found += [
                collection(f"{base}/dem_1m/2193/collection.json", f"DEM {survey}", 10000, reach),
                collection(f"{base}/dsm_1m/2193/collection.json", f"DSM {survey}", 10000, reach),
            ]
        if self.gappy_newer:  # the gappy survey is the newer
            found = [
                replace(c, end="2026-01-01T00:00:00Z") if "gappy" in c.url else c for c in found
            ]
        return found

    def aerials_for(self, region: str, bbox: BBox) -> Iterator[tuple[Collection, list[str]]]:
        for name in (
            ("gappy_2026_0.075m", "b_2025_0.075m") if self.gappy_newer else ("b_2025_0.075m",)
        ):
            url = f"{IMAGERY}/west-coast/{name}/rgb/2193/collection.json"
            aerial = collection(url, f"Aerial {name}", 1000, bbox, 0.075)
            yield (
                aerial,
                [f"https://example.test/{name}/{t}.tiff" for t in tiles_covering(bbox, 1000)],
            )


def join(tiles: Sequence[str], bbox: BBox, path: Path) -> Path:
    """A flat 100 m ground (DEM) or surface (DSM) covering ``bbox`` exactly."""
    west, south, east, north = bbox
    fill = -9999.0 if "gappy" in tiles[0] else 100.0  # a survey whose tile is empty here
    cells = np.full((1, int(north - south), int(east - west)), fill, dtype=np.float32)
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": cells.shape[2],
        "height": cells.shape[1],
        "count": 1,
        "crs": "EPSG:2193",
        "transform": rio.transform.from_origin(west, north, 1.0, 1.0),
        "nodata": -9999.0,
    }
    with rio.open(path, "w", **profile) as out:
        out.write(cells)
    return path


def read_aerial(tiles: Sequence[str], bbox: BBox, pixel_m: float) -> NDArray[np.uint8]:
    if "gappy" in tiles[0]:
        raise ValueError(f"{bbox} is not covered by {list(tiles)}")
    rows, cols = round((bbox[3] - bbox[1]) / pixel_m), round((bbox[2] - bbox[0]) / pixel_m)
    return np.full((rows, cols, 3), 90, dtype=np.uint8)


def no_masks(image: NDArray[np.uint8], concept: str) -> list[Mask]:
    return []


def sources(
    parcels: list[dict[str, Any]] = PARCELS,
    lidar: bool = True,
    gappy_newer: bool = False,
    point: list[float] = POINT,
) -> Sources:
    found = layers(parcels, point)
    return Sources(
        addresses=found["LINZ_NZ_Addresses"],
        parcels=found["LINZ_NZ_Primary_Parcels"],
        buildings=found["LINZ_NZ_Building_Outlines"],
        roads=found["LINZ_NZ_Addresses_Roads"],
        catalogues=FakeCatalogues(lidar, gappy_newer),
        segment=no_masks,
        join=join,
        read_aerial=read_aerial,
    )


def test_a_site_is_built_from_every_parcel_on_the_addresss_title(tmp_path: Path) -> None:
    steps: list[str] = []
    build_site(7, tmp_path, sources(), steps.append)
    assert steps == ["parcels", "terrain", "aerial", "survey"]
    site = load_demo_site(tmp_path)  # the manifest passes the demo site's own checks
    assert site.name == "1 Test Street, Reefton"
    assert site.title == "354613"
    assert [p.parcel_id for p in site.parcels] == [1, 2]  # not 3, on title 3546130
    assert site.valuation_number is None
    assert site.rasters["dem"].tiles and site.rasters["dem"].asset == str(tmp_path / "dem.tif")
    assert site.vectors["parcels"].licence == "CC-BY-4.0"
    assert any("legal boundaries" in item for item in site.open_items)
    survey = json.loads((tmp_path / "survey.geojson").read_text())
    assert survey["model"] == "sam-3.1" and survey["features"] == []
    manifest = json.loads((tmp_path / "site.json").read_text())
    assert manifest["address"]["linz_address_id"] == 7
    assert (tmp_path / "aerial.png").is_file() and len(manifest["aerial_bbox"]) == 4


def test_no_lidar_says_so_and_leaves_no_manifest(tmp_path: Path) -> None:
    with pytest.raises(NoLidar, match="no LINZ 1 m LiDAR"):
        build_site(7, tmp_path, sources(lidar=False), lambda _: None)
    assert not (tmp_path / "site.json").exists()


def test_an_address_on_no_title_is_refused(tmp_path: Path) -> None:
    untitled = [parcel(1, A, None)]
    with pytest.raises(SiteError, match="record of title"):
        build_site(7, tmp_path, sources(untitled), lambda _: None)


def test_a_title_bigger_than_a_section_is_refused(tmp_path: Path) -> None:
    far = X0 + MAX_SIDE_M + 50
    huge = [[X0, Y0], [far, Y0], [far, Y0 + 30], [X0, Y0 + 30], [X0, Y0]]
    with pytest.raises(SiteError, match="more than a section"):
        build_site(7, tmp_path, sources([parcel(1, huge, "1")]), lambda _: None)


def test_a_survey_with_a_gap_over_the_site_gives_way_to_an_older_one(tmp_path: Path) -> None:
    build_site(7, tmp_path, sources(gappy_newer=True), lambda _: None)
    assert load_demo_site(tmp_path).rasters["dem"].title == "DEM wc_2022"


def test_a_courtyard_building_keeps_its_hole(tmp_path: Path) -> None:
    build_site(7, tmp_path, sources(), lambda _: None)
    (outline,) = json.loads((tmp_path / "buildings.geojson").read_text())["features"]
    assert outline["id"] == "9" and len(outline["geometry"]["coordinates"]) == 2


def test_a_parcel_with_land_within_it_that_isnt_its_own_is_refused(tmp_path: Path) -> None:
    hole = [
        [X0 + 5, Y0 + 5],
        [X0 + 10, Y0 + 5],
        [X0 + 10, Y0 + 10],
        [X0 + 5, Y0 + 10],
        [X0 + 5, Y0 + 5],
    ]
    holed = parcel(1, A, "354613")
    holed["geometry"]["coordinates"] = [A, hole]
    with pytest.raises(SiteError, match="isn't its own"):
        build_site(7, tmp_path, sources([holed]), lambda _: None)


def test_an_aerial_with_a_gap_over_the_site_gives_way_to_the_next(tmp_path: Path) -> None:
    build_site(7, tmp_path, sources(gappy_newer=True), lambda _: None)
    assert load_demo_site(tmp_path).rasters["aerial"].title == "Aerial b_2025_0.075m"


def test_an_address_on_a_parcel_edge_is_on_the_parcel(tmp_path: Path) -> None:
    found = layers(PARCELS, point=[X0 + 20.0, Y0 + 15.0])  # on the line between A and B
    edge = Sources(
        addresses=found["LINZ_NZ_Addresses"],
        parcels=found["LINZ_NZ_Primary_Parcels"],
        buildings=found["LINZ_NZ_Building_Outlines"],
        roads=found["LINZ_NZ_Addresses_Roads"],
        catalogues=FakeCatalogues(),
        segment=no_masks,
        join=join,
        read_aerial=read_aerial,
    )
    build_site(7, tmp_path, edge, lambda _: None)
    assert load_demo_site(tmp_path).name == "1 Test Street, Reefton"


def test_a_record_that_fails_its_own_checks_leaves_the_site_unbuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuses(directory: Path) -> object:
        raise ValueError("the address point is not inside any parcel")

    monkeypatch.setattr("button_nz.sites.build.load_demo_site", refuses)
    with pytest.raises(SiteError, match="doesn't pass its own checks"):
        build_site(7, tmp_path, sources(), lambda _: None)
    assert not (tmp_path / "site.json").exists()


def test_an_address_on_the_line_between_two_titles_is_refused(tmp_path: Path) -> None:
    neighbours = [parcel(1, A, "354613"), parcel(2, B, "999999")]
    found = layers(neighbours, point=[X0 + 20.0, Y0 + 15.0])
    edge = Sources(
        addresses=found["LINZ_NZ_Addresses"],
        parcels=found["LINZ_NZ_Primary_Parcels"],
        buildings=found["LINZ_NZ_Building_Outlines"],
        roads=found["LINZ_NZ_Addresses_Roads"],
        catalogues=FakeCatalogues(),
        segment=no_masks,
        join=join,
        read_aerial=read_aerial,
    )
    with pytest.raises(SiteError, match="boundary between titles 354613 and 999999"):
        build_site(7, tmp_path, edge, lambda _: None)


def test_a_site_knows_which_edges_face_its_street(tmp_path: Path) -> None:
    build_site(7, tmp_path, sources(), lambda _: None)
    found = load_demo_site(tmp_path).frontages
    assert found is not None
    assert [(f.road, f.street) for f in found] == [("Test Street", True)]
    (street,) = found
    assert all(a[1] == Y0 and b[1] == Y0 for a, b in street.edges)  # the south side


def test_a_title_with_no_address_is_built_from_its_parcel(tmp_path: Path) -> None:
    found = sources()
    name = title_site_name(found.addresses, found.parcels, 3)  # parcel C, title 3546130
    build_title_site(3, name, tmp_path, found, lambda _: None)
    site = load_demo_site(tmp_path)
    assert site.name == "Lot 3, beside 1 Test Street, Reefton"  # its appellation, and where
    assert [p.parcel_id for p in site.parcels] == [3]
    assert site.frontages is not None and not any(f.street for f in site.frontages)


def test_a_parcel_with_no_title_is_never_built(tmp_path: Path) -> None:
    untitled = [parcel(4, A, None)]
    with pytest.raises(SiteError, match="record of title"):
        build_title_site(4, "Lot 4", tmp_path, sources(untitled), lambda _: None)


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _split(pid: int, x0: float, x1: float) -> dict[str, Any]:
    """A parcel a 4 m lane (y 12-16) cuts in two, as LINZ gives it: a MultiPolygon."""
    south, north = _box(X0 + x0, Y0, X0 + x1, Y0 + 12), _box(X0 + x0, Y0 + 16, X0 + x1, Y0 + 40)
    found = parcel(pid, south, "354613")
    found["geometry"] = {"type": "MultiPolygon", "coordinates": [[south], [north]]}
    return found


SPLIT = [_split(1, 0, 20), _split(2, 20, 40)]  # one title, both parcels cut by the lane


def test_a_title_a_road_cuts_in_two_is_built_on_the_addresss_side(tmp_path: Path) -> None:
    """33 Davis Street, Reefton (#136): a lane cuts both parcels on its title."""
    build_site(7, tmp_path, sources(SPLIT, point=[X0 + 10, Y0 + 6]), lambda _: None)
    site = load_demo_site(tmp_path)
    assert [p.parcel_id for p in site.parcels] == [1, 2]
    assert site.extent_nztm == (X0, Y0, X0 + 40, Y0 + 12)  # the south block only
    (left_out,) = [item for item in site.open_items if "across a road" in item]
    assert "960 m²" in left_out  # the north block: 40 x 24 m


def test_the_side_of_the_road_is_the_one_the_address_is_on(tmp_path: Path) -> None:
    build_site(7, tmp_path, sources(SPLIT, point=[X0 + 30, Y0 + 30]), lambda _: None)
    assert load_demo_site(tmp_path).extent_nztm == (X0, Y0 + 16, X0 + 40, Y0 + 40)


def test_a_title_site_a_road_cuts_in_two_is_built_on_its_larger_side(tmp_path: Path) -> None:
    found = sources(SPLIT)
    build_title_site(1, "Lot 1", tmp_path, found, lambda _: None)
    assert load_demo_site(tmp_path).extent_nztm == (X0, Y0 + 16, X0 + 40, Y0 + 40)
    assert title_site_name(found.addresses, found.parcels, 1).startswith("Lot 1")


def test_a_title_in_one_piece_leaves_nothing_out(tmp_path: Path) -> None:
    build_site(7, tmp_path, sources(), lambda _: None)
    assert not any("across a road" in item for item in load_demo_site(tmp_path).open_items)
