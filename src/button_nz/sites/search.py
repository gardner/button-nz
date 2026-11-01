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

from button_nz.geo.arcgis import FeatureLayer

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
