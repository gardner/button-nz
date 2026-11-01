"""Which edges of a title face a road, and which road: the address's own (its
street) or another. A brief can then mean something by "far from the street".

An edge faces a road when most of it runs along a LINZ road parcel
(``parcel_intent`` Road). The road is named from LINZ's addressing roads: the
nearest centreline within reach of the edge. The street is the address's own
road, matched by its LINZ ``road_id``, never by name. A road parcel with no
named road within reach is an unnamed frontage, not a guess.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from shapely import LineString, Polygon, union_all
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from button_nz.geo.arcgis import FeatureLayer
from button_nz.geo.geometry import BBox, Point, Ring, bounds

TOUCH_M = 0.5  # an edge this close to a road parcel runs along it
ALONG = 0.5  # the share of an edge that must run along road for it to face one
REACH_M = 40.0  # how far from an edge a road's centreline may be to name it
# LINZ NZ Addresses: Roads, the named roads addresses are on (CC BY 4.0).
LINZ_ADDRESS_ROADS = (
    "https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/"
    "LINZ_NZ_Addresses_Roads/FeatureServer/0"
)

type Edge = tuple[Point, Point]


@dataclass(frozen=True)
class Road:
    road_id: int  # LINZ's
    name: str
    centreline: BaseGeometry  # NZTM


@dataclass(frozen=True)
class Frontage:
    road: str | None  # its name; None if no named road is within reach
    street: bool  # the address's own road
    edges: tuple[Edge, ...]  # the title's boundary along it, NZTM
    # False for an address's street that runs along no edge of the title:
    # ``edges`` is then the one nearest it, ``distance_m`` away.
    adjacent: bool = True
    distance_m: float = 0.0


def frontages(
    title: Sequence[Ring],
    road_parcels: Sequence[BaseGeometry],
    roads: Sequence[Road],
    street_road_id: int,
) -> tuple[Frontage, ...]:
    """The title's frontages, one per road, in the order first met round its
    boundary."""
    edges = _boundary(title)
    found: dict[int | None, list[Edge]] = {}
    if road_parcels:
        along = union_all(list(road_parcels)).buffer(TOUCH_M)
        for edge in edges:
            line = LineString(edge)
            if line.length > 0 and line.intersection(along).length / line.length >= ALONG:
                found.setdefault(_road_of(line, roads), []).append(edge)
    names = {road.road_id: road.name for road in roads}
    fronting = [
        Frontage(None if rid is None else names[rid], rid == street_road_id, tuple(on))
        for rid, on in found.items()
    ]
    street = next((r for r in roads if r.road_id == street_road_id), None)
    if street is not None and not any(f.street for f in fronting):
        fronting.append(_away(street, edges))
    return tuple(fronting)


def _away(street: Road, edges: Sequence[Edge]) -> Frontage:
    """The address's street where it runs along no edge: the edge nearest it."""
    # The edge whose middle is nearest: two edges meeting at the corner
    # nearest the street are equally near at that corner.
    nearest = min(edges, key=lambda e: street.centreline.distance(_middle(e)))
    distance = round(street.centreline.distance(LineString(nearest)), 1)
    return Frontage(street.name, True, (nearest,), adjacent=False, distance_m=distance)


def _boundary(title: Sequence[Ring]) -> list[Edge]:
    """The outer boundary of the title's parcels together, edge by edge."""
    land = union_all([Polygon(ring) for ring in title])
    parts = getattr(land, "geoms", [land])
    edges: list[Edge] = []
    for part in parts:
        coords = [(float(x), float(y)) for x, y, *_ in part.exterior.coords]
        edges += [(a, b) for a, b in zip(coords, coords[1:], strict=False)]
    return edges


def _middle(edge: Edge) -> BaseGeometry:
    return LineString(edge).interpolate(0.5, normalized=True)


def _road_of(edge: LineString, roads: Sequence[Road]) -> int | None:
    """The named road nearest the edge's middle, if one is within reach."""
    middle = edge.interpolate(0.5, normalized=True)
    near = [(road.centreline.distance(middle), road.road_id) for road in roads]
    near = [(d, rid) for d, rid in near if d <= REACH_M]
    return min(near)[1] if near else None


def to_collection(found: Sequence[Frontage]) -> dict[str, Any]:
    """The frontages as NZTM GeoJSON, one MultiLineString per road."""
    return {
        "type": "FeatureCollection",
        "crs": "EPSG:2193",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "road": f.road,
                    "street": f.street,
                    "adjacent": f.adjacent,
                    "distance_m": f.distance_m,
                },
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [[list(a), list(b)] for a, b in f.edges],
                },
            }
            for f in found
        ],
    }


def from_collection(raw: dict[str, Any]) -> tuple[Frontage, ...]:
    """The frontages from ``to_collection``'s GeoJSON."""
    found: list[Frontage] = []
    for feature in raw["features"]:
        props, lines = feature["properties"], feature["geometry"]["coordinates"]
        road = props["road"]
        edges = tuple(((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))) for a, b in lines)
        name = None if road is None else str(road)
        adjacent, distance = bool(props["adjacent"]), float(props["distance_m"])
        found.append(Frontage(name, bool(props["street"]), edges, adjacent, distance))
    return tuple(found)


def describe_frontages(found: Sequence[Frontage] | None, local: Callable[[Point], Point]) -> str:
    """The frontages for the design agent, in its local coordinates. None
    (a site built before frontages were found) says it isn't known."""
    if found is None:
        return "- road frontages: not known for this site.\n"
    if not found:
        return "- road frontages: no edge of the title faces a road.\n"
    lines = ["- road frontages (title edges along a road, local x, y):"]
    for f in found:
        name = f.road or "an unnamed road"
        named = f"{name} (the address's street)" if f.street else name
        edges = "; ".join(_edge(edge, local) for edge in f.edges)
        if f.adjacent:
            lines.append(f"  - facing {named}: {edges}")
        else:
            lines.append(f"  - {named} runs along no edge: {f.distance_m:.1f} m from {edges}")
    return "\n".join(lines) + "\n"


def _edge(edge: Edge, local: Callable[[Point], Point]) -> str:
    (ax, ay), (bx, by) = local(edge[0]), local(edge[1])
    return f"({ax:.2f}, {ay:.2f}) to ({bx:.2f}, {by:.2f})"


def fetch_frontages(
    parcels: FeatureLayer, roads: FeatureLayer, title: Sequence[Ring], street_road_id: int
) -> tuple[Frontage, ...]:
    """The title's frontages from LINZ: the road parcels beside it (Primary
    Parcels with ``parcel_intent`` Road) and the named roads in reach of it."""
    reach = _grown(bounds([p for ring in title for p in ring]), REACH_M)
    road_parcels = [
        shape(f["geometry"])
        for f in parcels.in_envelope(reach).features
        if f["properties"].get("parcel_intent") == "Road" and f.get("geometry")
    ]
    named = [
        Road(
            int(f["properties"]["road_id"]),
            str(f["properties"]["full_road_name"]),
            shape(f["geometry"]),
        )
        for f in roads.in_envelope(reach).features
        if f.get("geometry")
    ]
    return frontages(title, road_parcels, named, street_road_id)


def _grown(bbox: BBox, by: float) -> BBox:
    west, south, east, north = bbox
    return (west - by, south - by, east + by, north + by)


def road_distances(walls: Ring, found: Sequence[Frontage] | None) -> str:
    """How far the walls are from each road the title faces (and from the
    edge nearest a street that runs along none), for the design agent's
    feedback: what "far from the street" can be judged by."""
    if not found:
        return ""
    footprint = Polygon(walls)
    lines = ["Distances from the roads (walls to the title's edge):"]
    for f in found:
        name = f.road or "an unnamed road"
        named = f"{name} (the address's street)" if f.street else name
        gap = min(footprint.distance(LineString(edge)) for edge in f.edges)
        beyond = "" if f.adjacent else f"; the street is {f.distance_m:.1f} m beyond it"
        lines.append(f"- {gap:.2f} m from the {named} edge{beyond}.")
    return "\n".join(lines)
