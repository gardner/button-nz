"""Search LINZ's national addresses for what a visitor typed.

The words go into an ArcGIS where clause, so only letters (macrons too),
digits, spaces and ``,.'/-`` are let through, 3 to 100 characters, and an
apostrophe is doubled. Every word must appear in the address; a leading
number must start it (``35 victory reefton`` finds 35 Victory Street).
"""

import re
from typing import Any, cast

from button_nz.geo.arcgis import FeatureLayer

MAX_RESULTS = 8
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


def search_addresses(layer: FeatureLayer, q: str) -> list[dict[str, Any]]:
    """At most ``MAX_RESULTS`` addresses matching ``q``, with their points in lon/lat."""
    found = layer.first(where_clause(q), MAX_RESULTS, out_sr=WGS84)
    results: list[dict[str, Any]] = []
    for feature in found.features:
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
