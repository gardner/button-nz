"""Tests for button_nz.sites.search: what a visitor types reaches LINZ's address
layer only as words it can't break out of."""

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from button_nz.geo.arcgis import FeatureLayer
from button_nz.sites.build import MAX_PARCELS, MAX_SIDE_M, SiteError, title_parcels
from button_nz.sites.search import (
    LOCAL_CANDIDATES,
    MAX_RESULTS,
    NotASection,
    QueryError,
    address_on_section,
    ground_distance,
    search_addresses,
    title_key,
    where_clause,
)
from test_sites_build import PARCELS, X0, Y0, layers, parcel  # noqa: E402
from test_sites_build import A as A_RING
from test_sites_build import B as B_RING

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


def test_nearest_is_by_ground_distance_not_raw_degrees() -> None:
    # Near Reefton a degree of longitude is about 0.74 of a degree of latitude:
    # 0.10 deg east (about 8.3 km) is nearer than 0.08 deg north (about 8.9 km).
    east = {"lonlat": [REEFTON[0] + 0.10, REEFTON[1]]}
    north = {"lonlat": [REEFTON[0], REEFTON[1] + 0.08]}
    assert sorted([north, east], key=lambda a: ground_distance(a["lonlat"], REEFTON)) == [
        east,
        north,
    ]


def test_more_local_candidates_are_asked_for_than_are_shown() -> None:
    seen: list[dict[str, str]] = []
    search_addresses(places_layer(seen), "12 st", near=REEFTON)
    assert int(seen[0]["resultRecordCount"]) == LOCAL_CANDIDATES > MAX_RESULTS


def _section_layers(
    parcels: list[dict[str, Any]], asked: list[str]
) -> tuple[FeatureLayer, FeatureLayer]:
    """LINZ's parcels (from test_sites_build's fake) and an address layer that
    counts what it is asked."""
    found = layers(parcels)

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return found["LINZ_NZ_Addresses"].client.get(str(request.url))

    counted = FeatureLayer(
        URL, "CC-BY-4.0", "LINZ", httpx.Client(transport=httpx.MockTransport(handler))
    )
    return counted, found["LINZ_NZ_Primary_Parcels"]


def test_a_section_without_an_address_asks_for_its_titles_addresses_once() -> None:
    asked: list[str] = []
    addresses, parcels = _section_layers(PARCELS, asked)
    assert address_on_section(addresses, parcels, 2) == 7  # B, by A's address on its title
    assert len(asked) == 1  # one envelope for the title, not one per parcel


def test_a_title_bigger_than_a_section_is_refused_before_any_address_is_asked() -> None:
    def lot(i: int) -> list[list[float]]:
        x = X0 + 100 + 10 * i  # none of them holds the address
        return [[x, Y0], [x + 10, Y0], [x + 10, Y0 + 10], [x, Y0 + 10], [x, Y0]]

    big = [parcel(100 + i, lot(i), "999") for i in range(MAX_PARCELS + 1)]
    asked: list[str] = []
    addresses, parcels = _section_layers(big, asked)
    with pytest.raises(NotASection, match="more than a section"):
        address_on_section(addresses, parcels, 100)
    assert asked == []


def test_a_parcel_on_more_titles_than_a_section_has_is_refused_before_asking_for_them() -> None:
    many = ", ".join(str(500000 + n) for n in range(MAX_PARCELS + 1))  # a unit-title base
    base = parcel(100, [[X0, Y0], [X0 + 9, Y0], [X0 + 9, Y0 + 9], [X0, Y0 + 9], [X0, Y0]], many)
    asked: list[str] = []
    addresses, parcels = _section_layers([base], asked)
    with pytest.raises(SiteError, match="more than a section"):
        address_on_section(addresses, parcels, 100)
    assert asked == []


def test_a_sections_titles_parcels_are_asked_for_in_one_query() -> None:
    two = ", ".join(("354613", "354614"))
    lots = [
        parcel(1, A_RING, two),
        parcel(2, B_RING, "354614"),
    ]
    queries: list[str] = []
    layer = layers(lots)["LINZ_NZ_Primary_Parcels"]
    counted = FeatureLayer(
        layer.url,
        "CC-BY-4.0",
        "LINZ",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: (queries.append(str(r.url)), layer.client.get(str(r.url)))[1]
            )
        ),
    )
    assert [_id(p) for p in title_parcels(counted, lots[0])] == [1, 2]
    assert len(queries) == 1


def _id(feature: Any) -> int:
    return int(feature["properties"]["id"])


def test_a_parcel_with_no_record_of_title_is_refused_not_built() -> None:
    lot = parcel(5, A_RING, None)  # holds the address, but no title: never a site
    asked: list[str] = []
    addresses, parcels = _section_layers([lot], asked)
    with pytest.raises(NotASection, match="record of title"):
        address_on_section(addresses, parcels, 5)
    assert asked == []


def test_a_title_site_is_keyed_by_a_parcel_on_exactly_the_tapped_parcels_titles() -> None:
    """A shared access lot (id 10, titles 800 and 900) has the smallest id, but
    keying on it would read back both titles and build the neighbour's too."""
    lot = [[X0 + 50, Y0], [X0 + 60, Y0], [X0 + 60, Y0 + 10], [X0 + 50, Y0 + 10], [X0 + 50, Y0]]
    section = [[X0 + 60, Y0], [X0 + 80, Y0], [X0 + 80, Y0 + 20], [X0 + 60, Y0 + 20], [X0 + 60, Y0]]
    parcels = layers(
        [parcel(10, lot, "800, 900"), parcel(20, section, "900"), parcel(5, section, "900")]
    )["LINZ_NZ_Primary_Parcels"]
    assert title_key(parcels, 20) == 5  # on 900 alone, as 20 is: not the shared lot
    assert title_key(parcels, 10) == 10  # the shared lot's own titles: only itself


def test_a_tapped_block_is_measured_not_the_whole_title_a_road_cuts() -> None:
    """Two blocks of one title further apart than a section is wide: each is a
    section, so tapping one isn't refused as more than a section."""
    near = parcel(1, A_RING, "354613")
    x = X0 + MAX_SIDE_M + 100
    far = parcel(2, [[x, Y0], [x + 20, Y0], [x + 20, Y0 + 30], [x, Y0 + 30], [x, Y0]], "354613")
    asked: list[str] = []
    addresses, parcels = _section_layers([near, far], asked)
    assert address_on_section(addresses, parcels, 1) == 7  # the fake's address, on A


def test_a_titles_blocks_far_apart_are_each_asked_for_addresses_not_the_land_between() -> None:
    """Blocks of one title kilometres apart: one envelope over both would page
    through a town's addresses. Each block's own envelope is asked instead."""
    near = parcel(1, A_RING, "354613")
    far = parcel(2, _sq(X0 + 5000, Y0, 20), "354613")
    asked: list[str] = []
    addresses, parcels = _section_layers([near, far], asked)
    assert address_on_section(addresses, parcels, 1) == 7
    assert all(width <= MAX_SIDE_M for width in _widths(asked))


def _addresses(
    points: list[tuple[int, list[float]]], asked: list[str] | None = None
) -> FeatureLayer:
    """An address layer serving these addresses, whatever envelope is asked;
    each request's URL kept in ``asked``."""
    features = [
        {
            "type": "Feature",
            "properties": {"address_id": aid, "full_address": f"{aid} Test Street"},
            "geometry": {"type": "Point", "coordinates": xy},
        }
        for aid, xy in points
    ]
    body = json.dumps({"type": "FeatureCollection", "features": features})

    def handler(request: httpx.Request) -> httpx.Response:
        if asked is not None:
            asked.append(str(request.url))
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FeatureLayer(URL, "CC-BY-4.0", "LINZ", client)


def _multi(pid: int, rings: list[list[list[float]]], titles: str) -> dict[str, Any]:
    found = parcel(pid, rings[0], titles)
    found["geometry"] = {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
    return found


def _sq(x: float, y: float, side: float) -> list[list[float]]:
    return [[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]


def test_an_address_on_the_tapped_block_beats_one_on_the_sections_far_piece() -> None:
    """Parcel 1: a big piece here and a small one across a lane. Its block here
    holds parcel 2's address (8); the far piece holds 9. The site is built here."""
    one = _multi(1, [_sq(X0, Y0, 30), _sq(X0, Y0 + 40, 10)], "354613")
    two = parcel(2, _sq(X0 + 30, Y0, 30), "354613")
    parcels = layers([one, two])["LINZ_NZ_Primary_Parcels"]
    addresses = _addresses([(9, [X0 + 5, Y0 + 45]), (8, [X0 + 45, Y0 + 15])])
    assert address_on_section(addresses, parcels, 1) == 8


def test_a_far_piece_of_the_tapped_section_doesnt_make_its_block_too_big() -> None:
    one = _multi(1, [_sq(X0, Y0, 30), _sq(X0 + MAX_SIDE_M + 100, Y0, 10)], "354613")
    parcels = layers([one])["LINZ_NZ_Primary_Parcels"]
    assert address_on_section(_addresses([(8, [X0 + 15, Y0 + 15])]), parcels, 1) == 8


def test_a_title_site_is_keyed_by_a_parcel_on_the_tapped_block() -> None:
    """Lot 1 and Lot 2 on one title, a neighbour between: tapping Lot 2 keys
    Lot 2's block, not Lot 1 (the title's smallest id) across the gap."""
    small = parcel(1, _sq(X0, Y0, 10), "354613")
    large = parcel(2, _sq(X0 + 30, Y0, 40), "354613")
    parcels = layers([small, large])["LINZ_NZ_Primary_Parcels"]
    assert title_key(parcels, 2) == 2
    assert title_key(parcels, 1) == 1


def test_a_parcel_in_touching_pieces_counts_once_toward_a_tapped_blocks_parcels() -> None:
    lots = [parcel(i, _sq(X0 + 10 * i, Y0, 10), "354613") for i in range(1, MAX_PARCELS)]
    wrapped = _multi(MAX_PARCELS, [_sq(X0, Y0, 10), _sq(X0, Y0 + 10, 10)], "354613")
    parcels = layers([*lots, wrapped])["LINZ_NZ_Primary_Parcels"]
    assert address_on_section(_addresses([(8, [X0 + 15, Y0 + 5])]), parcels, 1) == 8


def _widths(asked: list[str]) -> list[float]:
    """How wide or tall each envelope asked of the address layer was, in m."""
    found: list[float] = []
    for url in asked:
        west, south, east, north = map(
            float, parse_qs(urlsplit(url).query)["geometry"][0].split(",")
        )
        found.append(max(east - west, north - south))
    return found


def test_a_block_too_big_for_a_site_is_never_asked_for_its_addresses() -> None:
    """A small block of the title with no address; the title's address is on a
    farm block across a road, wider than a section. The farm's addresses are
    never paged through, and the tap builds the small block as a title site."""
    small = parcel(1, _sq(X0, Y0, 10), "354613")
    farm = parcel(2, _sq(X0 + 30, Y0, MAX_SIDE_M + 5000), "354613")
    parcels = layers([small, farm])["LINZ_NZ_Primary_Parcels"]
    asked: list[str] = []
    assert address_on_section(_addresses([(8, [X0 + 50, Y0 + 15])], asked), parcels, 1) is None
    assert _widths(asked) == [10]


def test_an_address_on_the_tapped_block_asks_no_other_block() -> None:
    near = parcel(1, _sq(X0, Y0, 20), "354613")
    far = parcel(2, _sq(X0 + 5000, Y0, 20), "354613")
    parcels = layers([near, far])["LINZ_NZ_Primary_Parcels"]
    asked: list[str] = []
    addresses = _addresses([(8, [X0 + 5, Y0 + 5]), (9, [X0 + 5005, Y0 + 5])], asked)
    assert address_on_section(addresses, parcels, 1) == 8
    assert len(asked) == 1


def test_with_no_address_on_its_block_the_nearest_block_with_one_is_taken() -> None:
    """Asked nearest first, stopping at the first block with an address."""
    tapped = parcel(1, _sq(X0, Y0, 10), "354613")
    near = parcel(2, _sq(X0 + 30, Y0, 10), "354613")
    far = parcel(3, _sq(X0 + 90, Y0, 10), "354613")
    parcels = layers([tapped, far, near])["LINZ_NZ_Primary_Parcels"]
    asked: list[str] = []
    addresses = _addresses([(9, [X0 + 95, Y0 + 5]), (8, [X0 + 35, Y0 + 5])], asked)
    assert address_on_section(addresses, parcels, 1) == 8
    assert len(asked) == 2  # the tapped block, then the near one: never the far one


def test_a_title_in_more_blocks_than_a_sections_parcels_is_refused_past_its_own() -> None:
    tapped = parcel(1, _sq(X0, Y0, 10), "354613")
    rest = [parcel(2 + i, _sq(X0 + 30 * (i + 1), Y0, 10), "354613") for i in range(MAX_PARCELS + 1)]
    parcels = layers([tapped, *rest])["LINZ_NZ_Primary_Parcels"]
    asked: list[str] = []
    with pytest.raises(NotASection, match="more than a section"):
        address_on_section(_addresses([], asked), parcels, 1)
    assert len(asked) == 1  # only its own block


def test_the_tapped_block_counts_toward_a_titles_blocks() -> None:
    """The tapped block and a section's most parcels of other blocks: one more
    block than a section's parcels."""
    tapped = parcel(1, _sq(X0, Y0, 10), "354613")
    rest = [parcel(2 + i, _sq(X0 + 30 * (i + 1), Y0, 10), "354613") for i in range(MAX_PARCELS)]
    parcels = layers([tapped, *rest])["LINZ_NZ_Primary_Parcels"]
    with pytest.raises(NotASection, match=f"{MAX_PARCELS + 1} blocks"):
        address_on_section(_addresses([]), parcels, 1)
