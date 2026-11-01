"""Tests for button_nz.geo.arcgis, driven by httpx.MockTransport."""

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from button_nz.geo.arcgis import ArcGISError, FeatureLayer

URL = "https://example.test/arcgis/rest/services/Things/FeatureServer/0"


def _collection(n: int, start: int = 0, more: bool = False) -> dict[str, object]:
    features = [
        {"type": "Feature", "properties": {"OBJECTID": i}, "geometry": None}
        for i in range(start, start + n)
    ]
    body: dict[str, object] = {"type": "FeatureCollection", "features": features}
    if more:
        body["properties"] = {"exceededTransferLimit": True}
    return body


def _layer(
    respond: Callable[[dict[str, str]], httpx.Response],
) -> tuple[FeatureLayer, list[dict[str, str]]]:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert urlsplit(str(request.url)).path.endswith("/FeatureServer/0/query")
        params = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        seen.append(params)
        return respond(params)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FeatureLayer(URL, "CC-BY-4.0", "Example Council", client), seen


def _ok(body: object) -> httpx.Response:
    return httpx.Response(200, text=json.dumps(body))


def test_where_query_returns_features_with_provenance() -> None:
    layer, seen = _layer(lambda _: _ok(_collection(2)))
    result = layer.where("ValNum='1'")
    assert [f["properties"]["OBJECTID"] for f in result.features] == [0, 1]
    assert seen[0]["where"] == "ValNum='1'"
    assert seen[0]["f"] == "geojson"
    assert seen[0]["outSR"] == "2193"
    assert seen[0]["outFields"] == "*"
    assert result.provenance.service == URL
    assert result.provenance.query["where"] == "ValNum='1'"
    assert result.provenance.licence == "CC-BY-4.0"
    assert result.provenance.attribution == "Example Council"
    assert result.provenance.retrieved_at.tzinfo is not None


def test_envelope_query_sends_an_nztm_envelope() -> None:
    layer, seen = _layer(lambda _: _ok(_collection(0)))
    layer.in_envelope((1.0, 2.0, 3.0, 4.0))
    assert seen[0]["geometry"] == "1.0,2.0,3.0,4.0"
    assert seen[0]["geometryType"] == "esriGeometryEnvelope"
    assert seen[0]["inSR"] == "2193"
    assert seen[0]["spatialRel"] == "esriSpatialRelIntersects"


def test_envelope_query_can_also_filter_by_attributes() -> None:
    layer, seen = _layer(lambda _: _ok(_collection(0)))
    result = layer.in_envelope((1.0, 2.0, 3.0, 4.0), where="ZONING='re'")
    assert seen[0]["where"] == "ZONING='re'"
    assert seen[0]["geometry"] == "1.0,2.0,3.0,4.0"
    assert result.provenance.query["where"] == "ZONING='re'"


def test_near_query_sends_a_point_and_distance_in_metres() -> None:
    layer, seen = _layer(lambda _: _ok(_collection(0)))
    layer.near((10.5, 20.5), 60.0)
    assert seen[0]["geometry"] == "10.5,20.5"
    assert seen[0]["geometryType"] == "esriGeometryPoint"
    assert seen[0]["distance"] == "60.0"
    assert seen[0]["units"] == "esriSRUnit_Meter"


def test_pages_until_the_transfer_limit_is_no_longer_exceeded() -> None:
    def respond(params: dict[str, str]) -> httpx.Response:
        offset = int(params.get("resultOffset", "0"))
        return _ok(_collection(2, start=offset, more=offset < 4))

    layer, seen = _layer(respond)
    result = layer.where("1=1")
    assert [f["properties"]["OBJECTID"] for f in result.features] == [0, 1, 2, 3, 4, 5]
    assert [p.get("resultOffset", "0") for p in seen] == ["0", "2", "4"]
    assert all(p["orderByFields"] == "OBJECTID" for p in seen)


def test_an_error_body_raises() -> None:
    error = {"error": {"code": 400, "message": "", "details": ["Invalid field: nope"]}}
    layer, _ = _layer(lambda _: _ok(error))
    with pytest.raises(ArcGISError, match="Invalid field: nope"):
        layer.where("nope=1")


def test_an_http_error_raises() -> None:
    layer, _ = _layer(lambda _: httpx.Response(503, text="unavailable"))
    with pytest.raises(ArcGISError, match="503"):
        layer.where("1=1")
