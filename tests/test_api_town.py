"""Tests for the town map and the aerial tiles over HTTP (button_nz.api.town)."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from button_nz.api.town import TownMaps, tiles_router, town_router
from button_nz.geo.arcgis import FeatureLayer

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


def town_app(tmp_path: Path, seen: list[str], held: tuple[int, ...] = (1, 2, 3)) -> TestClient:
    maps = TownMaps({"reefton": results(tmp_path)}, parcels_layer(seen, held), tmp_path / "town")
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
