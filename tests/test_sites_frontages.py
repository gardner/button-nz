"""Tests for button_nz.sites.frontages: which title edges face a road, and which road."""

from types import SimpleNamespace
from typing import Any

import pytest
from shapely import LineString, Polygon

from button_nz.sites.frontages import (
    Road,
    describe_frontages,
    fetch_frontages,
    from_collection,
    frontages,
    to_collection,
)

# A 20 m x 30 m title at the origin: Coal Street (the address's road) along
# its south side, Curle Street along its west, a neighbour to the north and east.
TITLE = ((0.0, 0.0), (20.0, 0.0), (20.0, 30.0), (0.0, 30.0), (0.0, 0.0))
SOUTH_ROAD = Polygon([(-20, -15), (40, -15), (40, 0), (-20, 0)])
WEST_ROAD = Polygon([(-15, -15), (0, -15), (0, 50), (-15, 50)])
COAL = Road(1, "Coal Street", LineString([(-20, -7.5), (40, -7.5)]))
CURLE = Road(2, "Curle Street", LineString([(-7.5, -15), (-7.5, 50)]))


def test_each_road_the_title_faces_is_named_and_the_street_is_the_addresss() -> None:
    found = frontages([TITLE], [SOUTH_ROAD, WEST_ROAD], [COAL, CURLE], street_road_id=1)
    by_road = {f.road: f for f in found}
    assert set(by_road) == {"Coal Street", "Curle Street"}
    assert by_road["Coal Street"].street and not by_road["Curle Street"].street
    assert by_road["Coal Street"].edges == (((0.0, 0.0), (20.0, 0.0)),)
    assert by_road["Curle Street"].edges == (((0.0, 30.0), (0.0, 0.0)),)


def test_a_road_parcel_with_no_named_road_in_reach_is_an_unnamed_frontage() -> None:
    found = frontages([TITLE], [SOUTH_ROAD], [], street_road_id=1)
    assert [(f.road, f.street) for f in found] == [(None, False)]


def test_a_title_with_no_road_beside_it_has_no_frontage_but_its_street_nearby() -> None:
    found = frontages([TITLE], [], [COAL], street_road_id=1)
    assert [(f.road, f.adjacent) for f in found] == [("Coal Street", False)]
    assert frontages([TITLE], [], [], street_road_id=1) == ()


def test_an_edge_only_touching_a_road_at_its_corner_doesnt_face_it() -> None:
    corner = Polygon([(-15, -15), (0, -15), (0, 0), (-15, 0)])  # meets the title at (0, 0)
    found = frontages([TITLE], [corner], [COAL], street_road_id=1)
    assert all(not f.adjacent for f in found)  # only the street, as nearby


def test_frontages_survive_their_file() -> None:
    found = frontages([TITLE], [SOUTH_ROAD, WEST_ROAD], [COAL, CURLE], street_road_id=1)
    assert from_collection(to_collection(found)) == found


def test_muse_is_told_which_edges_face_which_road_and_which_is_the_street() -> None:
    found = frontages([TITLE], [SOUTH_ROAD, WEST_ROAD], [COAL, CURLE], street_road_id=1)
    text = describe_frontages(found, lambda p: (p[0] - 10, p[1] - 15))  # local: centred
    assert "Coal Street (the address's street)" in text
    assert "(-10.00, -15.00) to (10.00, -15.00)" in text  # its south edge, local
    assert "Curle Street" in text and "Curle Street (the address" not in text


def test_a_site_with_no_road_beside_it_says_so_and_an_unknown_one_says_that() -> None:
    assert "no edge of the title faces a road" in describe_frontages((), lambda p: p)
    assert "not known" in describe_frontages(None, lambda p: p)


def test_a_street_that_runs_along_no_edge_is_named_with_its_nearest_edge_and_distance() -> None:
    # Coal Street passes 20 m east of the title, with no road parcel between.
    coal_away = Road(1, "Coal Street", LineString([(40, -20), (40, 50)]))
    found = frontages([TITLE], [WEST_ROAD], [coal_away, CURLE], street_road_id=1)
    street = next(f for f in found if f.street)
    assert street.road == "Coal Street" and not street.adjacent
    assert street.edges == (((20.0, 0.0), (20.0, 30.0)),)  # the east edge, nearest it
    assert street.distance_m == 20.0
    text = describe_frontages(found, lambda p: p)
    assert "Coal Street (the address's street) runs along no edge: 20.0 m from" in text


class FakeLayer:
    """A LINZ layer answering envelopes with ``near`` and ids with ``by_id``."""

    def __init__(self, near: list[dict[str, Any]], by_id: list[dict[str, Any]]) -> None:
        self.near, self.by_id = near, by_id
        self.asked: list[str] = []

    def in_envelope(self, bbox: Any) -> Any:
        return SimpleNamespace(features=self.near)

    def where(self, clause: str) -> Any:
        self.asked.append(clause)
        return SimpleNamespace(features=self.by_id)


def _road_feature(rid: int, name: str, line: list[list[float]]) -> dict[str, Any]:
    props = {"road_id": rid, "full_road_name": name}
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "LineString", "coordinates": line},
    }


def test_a_street_far_beyond_reach_is_still_found_by_its_id() -> None:
    far = _road_feature(1, "Coal Street", [[100, -20], [100, 50]])  # 80 m east: a rear section
    roads = FakeLayer(near=[], by_id=[far])
    found = fetch_frontages(FakeLayer([], []), roads, [TITLE], street_road_id=1)
    assert [(f.road, f.street, f.adjacent, f.distance_m) for f in found] == [
        ("Coal Street", True, False, 80.0)
    ]
    assert roads.asked == ["road_id = 1"]


def test_a_street_linz_doesnt_have_is_an_error_not_a_site_without_one() -> None:
    with pytest.raises(LookupError, match="road 1"):
        fetch_frontages(FakeLayer([], []), FakeLayer([], []), [TITLE], street_road_id=1)


def test_an_unnamed_lane_beside_the_title_isnt_named_after_the_street_in_front() -> None:
    # Coal Street in front (south); a lane with no addressing road along the east side.
    lane = Polygon([(20, 0), (26, 0), (26, 50), (20, 50)])  # from the street's edge north
    south = Polygon([(-20, -15), (20, -15), (20, 0), (-20, 0)])
    found = frontages([TITLE], [south, lane], [COAL], street_road_id=1)
    by_road = {f.road: f for f in found}
    assert by_road["Coal Street"].edges == (((0.0, 0.0), (20.0, 0.0)),)  # only the front
    assert by_road[None].edges == (((20.0, 0.0), (20.0, 30.0)),)  # the lane: unnamed


def test_a_short_street_near_one_end_of_a_long_edge_is_nearest_that_edge() -> None:
    long_title = ((0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (0.0, 20.0), (0.0, 0.0))
    stub = Road(1, "Coal Street", LineString([(-5, -1), (2, -1)]))  # 1 m south, at the west end
    (street,) = frontages([long_title], [], [stub], street_road_id=1)
    assert street.edges == (((0.0, 0.0), (100.0, 0.0)),) and street.distance_m == 1.0
