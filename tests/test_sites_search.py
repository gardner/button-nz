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
