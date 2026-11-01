"""Search LINZ's national addresses for what a visitor typed.

The words go into an ArcGIS where clause, so only letters (macrons too),
digits, spaces and ``,.'/-`` are let through, 3 to 100 characters, and an
apostrophe is doubled. Every word must appear in the address; a leading
number must start it (``35 victory reefton`` finds 35 Victory Street).

Given where the visitor is looking (``near``, the map's centre), addresses
within ``NEAR_DEG`` of it come first, nearest first; the national matches
fill the rest of the list, each address once.
"""

import math
import re
from collections.abc import Sequence
from typing import Any, cast

from shapely import Point, unary_union
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from button_nz.geo.arcgis import Feature, FeatureLayer
from button_nz.sites.blocks import block
from button_nz.sites.build import MAX_PARCELS, MAX_SIDE_M, SiteError, title_parcels, titles_of

MAX_RESULTS = 8
NEAR_DEG = 0.25  # about 25 km each way: the town the map shows, and its neighbours
LOCAL_CANDIDATES = 50  # asked for near the map, then ranked: LINZ's own order isn't distance
WGS84 = "4326"
ALLOWED = re.compile(r"[^\W_]|[ ,.'/\-]")  # one allowed character: no underscore
WORD = re.compile(r"[^\W_][^\W_'/\-]*(?:['/\-][^\W_]+)*")


class QueryError(ValueError):
    """What was typed can't be searched for."""


def where_clause(q: str) -> str:
    """The where clause finding addresses with every word of ``q``."""
    if not 3 <= len(q) <= 100 or not all(ALLOWED.fullmatch(c) for c in q):
        raise QueryError("an address is 3-100 letters, digits, spaces and , . ' / -")
    words = [w.upper().replace("'", "''") for w in WORD.findall(q)]
    if not words:
        raise QueryError("type part of an address: a number and a street")
    likes = [f"UPPER(full_address) LIKE '%{w}%'" for w in words]
    if words[0].isdigit():
        likes[0] = f"UPPER(full_address) LIKE '{words[0]} %'"
    return " AND ".join(likes)


def search_addresses(
    layer: FeatureLayer, q: str, near: tuple[float, float] | None = None
) -> list[dict[str, Any]]:
    """At most ``MAX_RESULTS`` addresses matching ``q``, with their points in
    lon/lat; those near ``near`` (lon, lat) first, nearest first."""
    clause = where_clause(q)
    if near is None:
        return _addresses(layer.first(clause, MAX_RESULTS, out_sr=WGS84).features)
    lon, lat = near
    box = (lon - NEAR_DEG, lat - NEAR_DEG, lon + NEAR_DEG, lat + NEAR_DEG)
    local = _addresses(layer.first(clause, LOCAL_CANDIDATES, out_sr=WGS84, within=box).features)
    local = sorted(local, key=lambda a: ground_distance(a["lonlat"], near))[:MAX_RESULTS]
    if len(local) == MAX_RESULTS:
        return local
    seen = {a["id"] for a in local}
    rest = _addresses(layer.first(clause, MAX_RESULTS, out_sr=WGS84).features)
    return (local + [a for a in rest if a["id"] not in seen])[:MAX_RESULTS]


def ground_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """How far apart two lon/lat points are on the ground, in degrees of
    latitude: longitude scaled by the cosine of the latitude. Close enough to
    rank addresses within a town."""
    shrink = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * shrink, a[1] - b[1])


def _addresses(features: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for feature in features:
        props = cast("dict[str, Any]", feature["properties"])
        geometry = cast("dict[str, Any]", feature["geometry"])
        lon, lat = (float(v) for v in cast("list[float]", geometry["coordinates"])[:2])
        results.append(
            {
                "id": int(props["address_id"]),
                "address": str(props["full_address"]),
                "town": str(props.get("town_city") or ""),
                "lonlat": [lon, lat],
            }
        )
    return results


class NoSuchSection(LookupError):
    """LINZ has no primary parcel with that id."""


class NotASection(SiteError):
    """The parcel's title is more than a section: no site is built for it."""


def address_on_section(
    addresses: FeatureLayer, parcels: FeatureLayer, parcel_id: int
) -> int | None:
    """The LINZ address on primary parcel ``parcel_id``, so a section clicked on
    the map starts the same site as searching for it. A section with no address
    of its own takes one on another parcel of its title (one property), nearest
    the section's middle. None when the whole title has none.

    A title a road cuts in two is measured by the section's own block of it
    (``blocks.block``), which a site is built on, and an address on that block
    comes before one across the road. A block too big for a site
    (``MAX_PARCELS``, ``MAX_SIDE_M``, as ``find_title`` refuses) is refused
    before any address is asked for, and the title's addresses are asked for
    once, over its whole extent."""
    found = parcels.where(f"id = {int(parcel_id)}").features
    if not found:
        raise NoSuchSection(parcel_id)
    section = _shape(found[0])
    on_title = title_parcels(parcels, found[0])
    if not on_title:  # a road, a reserve: find_title would refuse its address too
        raise NotASection(f"parcel {parcel_id} has no record of title: it isn't a property")
    middle = section.representative_point()
    mine, _ = block(on_title, (float(middle.x), float(middle.y)))
    own = unary_union([section, *(_shape(p) for p in mine)])
    west, south, east, north = own.bounds
    if len(mine) > MAX_PARCELS or max(east - west, north - south) > MAX_SIDE_M:
        raise NotASection(
            f"parcel {parcel_id}'s title is {len(mine)} parcels over "
            f"{east - west:.0f} x {north - south:.0f} m: more than a section"
        )
    land = unary_union([section, *(_shape(p) for p in on_title)])
    on = [
        (not section.covers(point), not own.covers(point), section.centroid.distance(point), a)
        for point, a in _addresses_in(addresses, land)
    ]
    return min(on)[3] if on else None  # its own, its block's, then the nearest


def _shape(feature: Feature) -> BaseGeometry:
    return shape(cast("dict[str, Any]", feature["geometry"]))


def title_key(parcels: FeatureLayer, parcel_id: int) -> int:
    """The smallest id of a parcel on exactly parcel ``parcel_id``'s titles:
    what a title site with no address is kept by, whichever of them was
    tapped. A parcel on other titles too (a shared access lot) would read
    back more titles when the site is built, so it can't be the key."""
    found = parcels.where(f"id = {int(parcel_id)}").features
    if not found:
        raise NoSuchSection(parcel_id)
    titles = set(titles_of(found[0]))
    same = [p for p in title_parcels(parcels, found[0]) if set(titles_of(p)) == titles]
    return min([int(parcel_id), *(int(_props_of(p)["id"]) for p in same)])


def _props_of(feature: Feature) -> dict[str, Any]:
    return cast("dict[str, Any]", feature["properties"])


def _addresses_in(addresses: FeatureLayer, land: BaseGeometry) -> list[tuple[Point, int]]:
    """The addresses on ``land``, each at its point."""
    on: list[tuple[Point, int]] = []
    for feature in addresses.in_envelope(land.bounds).features:
        x, y = (float(v) for v in cast("dict[str, Any]", feature["geometry"])["coordinates"][:2])
        if land.covers(point := Point(x, y)):
            on.append((point, int(cast("dict[str, Any]", feature["properties"])["address_id"])))
    return on
