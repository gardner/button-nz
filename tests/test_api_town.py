"""Tests for the town map and the aerial tiles over HTTP (button_nz.api.town)."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from button_nz.api.town import TownMaps, tiles_router, town_router
from button_nz.geo.arcgis import FeatureLayer
from button_nz.geo.geometry import BBox
from button_nz.geo.terrain import TerrainGrid

X, Y = 1505930.0, 5336780.0


def square(x: float) -> list[list[float]]:
    return [[x, Y], [x + 20, Y], [x + 20, Y + 30], [x, Y + 30], [x, Y]]


def results(tmp_path: Path) -> Path:
    rows: list[dict[str, object]] = [
        {"parcel_id": 1, "fits_eaves": ["airhome-vista"], "clear_eaves": ["airhome-vista"]},
        {"parcel_id": 2, "fits_eaves": ["south-peak-okari"], "clear_eaves": []},
        {"parcel_id": 3, "fits_eaves": [], "clear_eaves": []},
    ]
    path = tmp_path / "results.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def parcels_layer(seen: list[str], held: tuple[int, ...] = (1, 2, 3)) -> FeatureLayer:
    def handler(request: httpx.Request) -> httpx.Response:
        where = parse_qs(urlsplit(str(request.url)).query)["where"][0]
        seen.append(where)
        features = [
            {
                "type": "Feature",
                "properties": {"id": i},
                "geometry": {"type": "Polygon", "coordinates": [square(X + 20 * i)]},
            }
            for i in (1, 2, 3)
            if i in held
            if str(i) in where
        ]
        return httpx.Response(
            200, text=json.dumps({"type": "FeatureCollection", "features": features})
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FeatureLayer(
        "https://example.test/LINZ_NZ_Primary_Parcels/FeatureServer/0", "CC-BY-4.0", "LINZ", client
    )


def outline(id_: str, west: float, south: float) -> dict[str, object]:
    ring = [[west, south], [west + 6, south], [west + 6, south + 8], [west, south + 8]]
    return {
        "type": "Feature",
        "id": id_,
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [[*ring, ring[0]]]},
    }


def outlines(asked: list[BBox]) -> Callable[[BBox], dict[str, object]]:
    """A house on section 1, and a shed 500 m away on no screened section."""

    def found(bbox: BBox) -> dict[str, object]:
        asked.append(bbox)
        house, shed = outline("11", X + 25, Y + 5), outline("12", X + 500, Y)
        return {"type": "FeatureCollection", "features": [house, shed]}

    return found


def lidar(asked: list[BBox]) -> Callable[[BBox], TerrainGrid]:
    """A flat town at 200 m with everything standing 4.5 m tall."""

    def grid(bbox: BBox) -> TerrainGrid:
        asked.append(bbox)
        x0, y0, x1, y1 = bbox
        shape = (round(y1 - y0), round(x1 - x0))
        return TerrainGrid(bbox, 1.0, np.full(shape, 200.0), np.full(shape, 4.5), ("fake",))

    return grid


def town_app(
    tmp_path: Path,
    seen: list[str],
    held: tuple[int, ...] = (1, 2, 3),
    asked: list[BBox] | None = None,
) -> TestClient:
    maps = TownMaps(
        {"reefton": results(tmp_path)},
        parcels_layer(seen, held),
        tmp_path / "town",
        outlines([] if asked is None else asked),
        lidar([] if asked is None else asked),
    )
    app = FastAPI()
    app.include_router(town_router(maps))
    return TestClient(app)


def test_each_section_is_coloured_by_what_the_screen_found(tmp_path: Path) -> None:
    seen: list[str] = []
    town = town_app(tmp_path, seen).get("/town/reefton").json()
    assert [(f["properties"]["id"], f["properties"]["category"]) for f in town["features"]] == [
        (1, "clear"),
        (2, "outlines"),
        (3, "none"),
    ]
    lon, lat = town["features"][0]["geometry"]["coordinates"][0][0]
    assert 171 < lon < 172 and -43 < lat < -42
    assert seen == ["id IN (1,2,3)"]
    assert town["missing"] == {"ids": [], "reason": "not in LINZ's NZ Primary Parcels"}


def test_the_town_is_read_once_and_kept(tmp_path: Path) -> None:
    seen: list[str] = []
    client = town_app(tmp_path, seen)
    client.get("/town/reefton")
    client.get("/town/reefton")
    assert len(seen) == 1
    assert len(list((tmp_path / "town").glob("reefton-*.geojson"))) == 1


def test_the_buildings_on_the_towns_sections_carry_their_heights(tmp_path: Path) -> None:
    asked: list[BBox] = []
    town = town_app(tmp_path, [], asked=asked).get("/town/reefton").json()
    (house,) = town["buildings"]["features"]  # the shed is on no screened section
    # On a town map each building stands on its own ground: base 0, top its height.
    assert house["id"] == "11"
    assert house["properties"] == {"base_m": 0.0, "height_m": 4.5, "above_ground_m": 4.5}
    lon, lat = house["geometry"]["coordinates"][0][0]
    assert 171 < lon < 172 and -43 < lat < -42
    sections, grid = asked
    assert sections == (X + 20, Y, X + 80, Y + 30)  # the outlines over the sections
    x0, y0, x1, y1 = grid  # the LiDAR over the house, in whole metres
    assert x0 <= X + 25 and y0 <= Y + 5 and x1 >= X + 31 and y1 >= Y + 13
    assert x1 - x0 < 10 and float(x0).is_integer()


def test_a_layer_cached_in_an_older_format_is_rebuilt_not_served(tmp_path: Path) -> None:
    version = hashlib.sha256(results(tmp_path).read_bytes()).hexdigest()[:12]
    old = tmp_path / "town" / f"reefton-{version}.geojson"  # the key before the format was in it
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"type": "FeatureCollection", "features": [], "missing": {}}))
    town = town_app(tmp_path, [], asked=[]).get("/town/reefton").json()
    assert "buildings" in town and len(town["features"]) == 3


def test_a_town_with_no_resolvable_sections_has_no_buildings_and_asks_for_none(
    tmp_path: Path,
) -> None:
    asked: list[BBox] = []
    town = town_app(tmp_path, [], held=(), asked=asked).get("/town/reefton").json()
    assert town["features"] == [] and town["missing"]["ids"] == [1, 2, 3]
    assert town["buildings"] == {"type": "FeatureCollection", "features": []}
    assert asked == []  # no outlines asked for over nothing


def test_a_section_linz_has_no_parcel_for_is_named_not_drawn(tmp_path: Path) -> None:
    town = town_app(tmp_path, [], held=(1, 3)).get("/town/reefton").json()
    assert [f["properties"]["id"] for f in town["features"]] == [1, 3]
    assert town["missing"] == {"ids": [2], "reason": "not in LINZ's NZ Primary Parcels"}


def test_new_screen_results_are_shown_not_the_old_layer(tmp_path: Path) -> None:
    seen: list[str] = []
    client = town_app(tmp_path, seen)
    client.get("/town/reefton")
    rescreened = [{"parcel_id": 3, "fits_eaves": ["airhome-vista"], "clear_eaves": []}]
    (tmp_path / "results.jsonl").write_text(json.dumps(rescreened[0]), encoding="utf-8")
    town = client.get("/town/reefton").json()
    assert [(f["properties"]["id"], f["properties"]["category"]) for f in town["features"]] == [
        (3, "outlines")
    ]


def test_a_broken_screen_is_an_error_not_a_missing_town(tmp_path: Path) -> None:
    client = town_app(tmp_path, [])
    (tmp_path / "results.jsonl").write_text('{"fits_eaves": []}', encoding="utf-8")
    with pytest.raises(KeyError):
        client.get("/town/reefton")


def test_a_layer_cut_off_mid_write_is_never_served(tmp_path: Path) -> None:
    def broken(*args: object, **kwargs: object) -> int:
        raise OSError("disk full")

    client = town_app(tmp_path, [])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "write_text", broken)
        with pytest.raises(OSError):
            client.get("/town/reefton")
    assert not list((tmp_path / "town").glob("*.geojson"))  # nothing half-made to read later
    assert len(client.get("/town/reefton").json()["features"]) == 3


def test_an_unknown_town_is_not_found(tmp_path: Path) -> None:
    assert town_app(tmp_path, []).get("/town/atlantis").status_code == 404


def tiles_app(key: str | None, seen: list[str]) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"RIFF....WEBP", headers={"content-type": "image/webp"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    app = FastAPI()
    app.include_router(tiles_router(client, lambda: key, "https://basemaps.example/v1/tiles"))
    return TestClient(app)


def test_a_tile_is_fetched_with_the_servers_key_and_never_shows_it() -> None:
    seen: list[str] = []
    tile = tiles_app("SECRET", seen).get("/tiles/aerial/18/258000/164000.webp")
    assert tile.status_code == 200 and tile.content == b"RIFF....WEBP"
    assert tile.headers["content-type"] == "image/webp"
    assert "max-age" in tile.headers["cache-control"]
    assert seen == [
        "https://basemaps.example/v1/tiles/aerial/WebMercatorQuad/18/258000/164000.webp?api=SECRET"
    ]
    assert b"SECRET" not in tile.content and "SECRET" not in str(tile.headers)


@pytest.mark.parametrize(
    "path",
    [
        "/tiles/aerial/23/0/0.webp",
        "/tiles/aerial/2/4/0.webp",
        "/tiles/aerial/2/0/-1.webp",
        "/tiles/aerial/a/0/0.webp",
    ],
)
def test_only_real_tiles_are_asked_for(path: str) -> None:
    seen: list[str] = []
    assert tiles_app("SECRET", seen).get(path).status_code in (404, 422)
    assert seen == []


def test_without_a_key_tiles_are_unavailable_and_say_why() -> None:
    tile = tiles_app(None, []).get("/tiles/aerial/1/0/0.webp")
    assert tile.status_code == 503 and "LINZ_BASEMAP_API_KEY" in tile.json()["detail"]
