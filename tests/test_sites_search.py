"""Tests for button_nz.sites.search: what a visitor types reaches LINZ's address
layer only as words it can't break out of."""

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from button_nz.geo.arcgis import FeatureLayer
from button_nz.sites.search import MAX_RESULTS, QueryError, search_addresses, where_clause

URL = "https://example.test/arcgis/rest/services/LINZ_NZ_Addresses/FeatureServer/0"


def addresses_layer(seen: list[dict[str, str]]) -> FeatureLayer:
    def handler(request: httpx.Request) -> httpx.Response:
        params = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        seen.append(params)
        feature = {
            "type": "Feature",
            "properties": {
                "address_id": 3213224,
                "full_address": "35 Victory Street, Reefton",
                "town_city": "Reefton",
            },
            "geometry": {"type": "Point", "coordinates": [171.862222, -42.115318]},
        }
        return httpx.Response(200, text=json.dumps({"features": [feature]}))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FeatureLayer(URL, "CC-BY-4.0", "LINZ", client)


def test_each_word_must_appear_and_a_leading_number_starts_the_address() -> None:
    assert where_clause("35 victory reefton") == (
        "UPPER(full_address) LIKE '35 %' AND UPPER(full_address) LIKE '%VICTORY%'"
        " AND UPPER(full_address) LIKE '%REEFTON%'"
    )


def test_an_apostrophe_is_doubled_so_it_stays_inside_the_string() -> None:
    assert where_clause("O'Connell St") == (
        "UPPER(full_address) LIKE '%O''CONNELL%' AND UPPER(full_address) LIKE '%ST%'"
    )


@pytest.mark.parametrize(
    "q",
    [
        "ab",  # too short
        "x" * 101,  # too long
        "1=1; DROP TABLE x",  # = and ;
        "12 Cuba St%",  # a wildcard of its own
        "12 Cuba_St",  # the other wildcard
        "a) OR (1=1",  # parentheses
        'say "hi" there',  # double quotes
        "   ",  # nothing but spaces
        "--- ,,, ...",  # punctuation, no word
    ],
)
def test_anything_but_letters_digits_spaces_and_the_allowed_marks_is_refused(q: str) -> None:
    with pytest.raises(QueryError):
        where_clause(q)


def test_macrons_are_letters() -> None:
    assert "TAUPŌ" in where_clause("1 Lake Terrace Taupō")


def test_a_search_returns_at_most_eight_addresses_in_lon_lat() -> None:
    seen: list[dict[str, str]] = []
    found = search_addresses(addresses_layer(seen), "35 Victory Reefton")
    assert seen[0]["resultRecordCount"] == str(MAX_RESULTS) == "8"
    assert seen[0]["outSR"] == "4326"
    assert found == [
        {
            "id": 3213224,
            "address": "35 Victory Street, Reefton",
            "town": "Reefton",
            "lonlat": [171.862222, -42.115318],
        }
    ]


REEFTON = (171.8622, -42.1153)


def places_layer(seen: list[dict[str, str]]) -> FeatureLayer:
    """National answers lead with Wellington and Auckland; asked within an
    envelope, only the Reefton ones come back."""
    near = [
        (1, "12 Broadway, Reefton", 171.8701, -42.1196),
        (2, "12 Shiel St, Reefton", 171.862, -42.116),
    ]
    far = [
        (3, "12 Cuba Street, Petone", 174.88, -41.22),
        (4, "12 Queen St, Auckland", 174.77, -36.85),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        params = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        seen.append(params)
        rows = list(reversed(near)) if "geometry" in params else far + near
        features = [
            {
                "type": "Feature",
                "properties": {"address_id": i, "full_address": a, "town_city": ""},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
            for i, a, lon, lat in rows
        ]
        return httpx.Response(200, text=json.dumps({"features": features}))

    return FeatureLayer(
        URL, "CC-BY-4.0", "LINZ", httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_addresses_near_the_map_come_first_nearest_first_then_the_rest() -> None:
    seen: list[dict[str, str]] = []
    found = search_addresses(places_layer(seen), "12 st", near=REEFTON)
    assert [a["id"] for a in found] == [2, 1, 3, 4]  # Reefton's, nearest first; then the rest, once
    local = seen[0]
    assert local["geometryType"] == "esriGeometryEnvelope" and local["inSR"] == "4326"
    assert local["spatialRel"] == "esriSpatialRelIntersects"


def test_without_a_place_the_search_is_national_as_before() -> None:
    seen: list[dict[str, str]] = []
    found = search_addresses(places_layer(seen), "12 st")
    assert [a["id"] for a in found] == [3, 4, 1, 2] and len(seen) == 1
