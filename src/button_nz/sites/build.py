"""Build a site to design on from any LINZ address, out of national open data:

1. **parcels:** the address point, the LINZ primary parcel under it, every
   parcel on the same record(s) of title, and the LINZ building outlines
   around them;
2. **terrain:** the newest 1 m DEM and DSM that both cover the site
   (``sites.stac``), joined from their tiles into one file each;
3. **aerial:** the region's best recent aerial over the same ground;
4. **survey:** SAM 3.1 on the aerial, checked against the LiDAR
   (``perception.survey``).

Each step's output is written to the site's directory, and the manifest
(``site.json``, read by ``demo_site.load_demo_site``) last, so a site with a
manifest is whole. A site the data can't support says why: ``SiteError`` for
a failure, or ``NoLidar`` where no LiDAR covers it. Nothing is ever filled in.
"""

import io
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from shapely import Point as ShapelyPoint
from shapely import Polygon, union_all
from shapely.geometry import shape

from button_nz.demo_site import load_demo_site
from button_nz.geo.arcgis import Feature, FeatureLayer
from button_nz.geo.geometry import BBox, Point, Ring, bounds
from button_nz.geo.property import LINZ, find_address
from button_nz.geo.terrain import TerrainGrid, read_terrain
from button_nz.perception.survey import CONCEPTS, PIXEL_M, Segment, survey, write_survey
from button_nz.sites.frontages import Frontage, fetch_frontages, to_collection
from button_nz.sites.stac import Catalogues, Collection, lidar_pairs

MAX_PARCELS = 12
NEAR_ADDRESS_M = 200.0  # how far to look for an address to place a title site by
MAX_SIDE_M = 200.0  # a site wider or taller than this is more than a section
TERRAIN_MARGIN_M = 25.0  # read past the site: the design scene's margin is 20 m
TITLE = r"[0-9A-Za-z/]+"

type Join = Callable[[Sequence[str], BBox, Path], Path]
type ReadAerial = Callable[[Sequence[str], BBox, float], NDArray[np.uint8]]


class SiteError(RuntimeError):
    """The open data can't make a site here, and why."""


class NoLidar(SiteError):
    """No LiDAR DEM and DSM cover the whole site."""


@dataclass(frozen=True)
class Sources:
    addresses: FeatureLayer  # LINZ NZ Addresses
    parcels: FeatureLayer  # LINZ NZ Primary Parcels
    buildings: FeatureLayer  # LINZ NZ Building Outlines
    roads: FeatureLayer  # LINZ NZ Addresses: Roads, to name the title's frontages
    catalogues: Catalogues
    segment: Segment  # SAM 3.1
    join: Join  # tiles into one raster (``town.lidar.mosaic``)
    read_aerial: ReadAerial  # ``geo.imagery.read_aerial``


@dataclass(frozen=True)
class Title:
    address: str
    point: Point
    titles: tuple[str, ...]
    parcels: tuple[Feature, ...]
    extent: BBox
    road_id: int | None = None  # the address's road, LINZ's
    addressed: bool = True  # False: a title with no address, built from its parcel


def build_site(
    address_id: int, directory: Path, sources: Sources, step: Callable[[str], None]
) -> None:
    """Build the site at LINZ address ``address_id`` into ``directory``,
    telling ``step`` which step it is on."""
    directory.mkdir(parents=True, exist_ok=True)
    step("parcels")
    _build(find_title(sources, address_id), address_id, directory, sources, step)


def build_title_site(
    parcel_id: int, directory: Path, sources: Sources, step: Callable[[str], None]
) -> None:
    """Build the site of LINZ parcel ``parcel_id``'s title, for a title with no
    address (a vacant section, say), into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    step("parcels")
    _build(title_of_parcel(sources, parcel_id), None, directory, sources, step)


def _build(
    title: Title,
    address_id: int | None,
    directory: Path,
    sources: Sources,
    step: Callable[[str], None],
) -> None:
    _write(directory / "parcels.geojson", _parcels_file(title))
    _write(directory / "frontages.geojson", to_collection(_frontages_of(title, sources)))
    outlines = sources.buildings.in_envelope(_grown(title.extent, TERRAIN_MARGIN_M))
    _write(directory / "buildings.geojson", outlines_collection(outlines.features))
    step("terrain")
    dem, dsm, grid = _terrain(title.extent, directory, sources)
    step("aerial")
    aerial, aerial_tiles, photo = _aerial(dem.region, grid, title.extent, sources)
    (directory / "aerial.png").write_bytes(photo)
    step("survey")
    site = union_all([Polygon(_ring(f)) for f in title.parcels])
    found = survey(sources.segment, aerial_pixels(photo), grid, grid.bbox, PIXEL_M, within=site)
    reach = _grown(title.extent, TERRAIN_MARGIN_M)
    lidar = [*cast("list[str]", dem.tiles_for(reach)), *cast("list[str]", dsm.tiles_for(reach))]
    write_survey(directory, found, _survey_meta(aerial, lidar))
    manifest = _manifest(address_id, title, (dem, dsm, aerial), aerial_tiles, sources)
    manifest["aerial_bbox"] = list(grid.bbox)  # what aerial.png covers, at PIXEL_M
    _write(directory / "site.json", manifest)
    try:
        load_demo_site(directory)  # as the routes will: a site is ready only if it loads
    except (ValueError, KeyError) as error:
        (directory / "site.json").unlink()
        raise SiteError(f"the site's record doesn't pass its own checks: {error}") from error


def find_title(sources: Sources, address_id: int) -> Title:
    """The address, and every parcel on the record(s) of title under its point."""
    address = find_address(sources.addresses, address_id).value
    point = ShapelyPoint(address.point)
    under = [f for f in sources.parcels.near(address.point, 0.0).features if _holds(f, point)]
    sets = {tuple(sorted(_titles(f))) for f in under if _titles(f)}
    if len(sets) > 1:  # on the line between two properties: whose is it?
        named = " and ".join(", ".join(s) for s in sorted(sets))
        raise SiteError(f"{address.full_address} is on the boundary between titles {named}")
    titles = sets.pop() if sets else ()
    if not titles:
        raise SiteError(f"{address.full_address} isn't on a parcel with a record of title")
    parcels, extent = _title_parcels(sources, titles)
    return Title(
        address.full_address, address.point, titles, tuple(parcels), extent, address.road_id
    )


def title_of_parcel(sources: Sources, parcel_id: int) -> Title:
    """The title LINZ parcel ``parcel_id`` is on, for a title with no address:
    named by the parcel's appellation and the nearest address, with no street."""
    found = sources.parcels.where(f"id = {int(parcel_id)}").features
    if not found:
        raise SiteError(f"LINZ has no parcel {parcel_id}")
    titles = tuple(sorted(_titles(found[0])))
    if not titles:
        raise SiteError(f"parcel {parcel_id} has no record of title: it isn't a property")
    parcels, extent = _title_parcels(sources, titles)
    middle = union_all([Polygon(_ring(f)) for f in parcels]).representative_point()
    point = (float(middle.x), float(middle.y))
    name = _named(found[0], point, sources)
    return Title(name, point, titles, tuple(parcels), extent, road_id=None, addressed=False)


def _named(parcel: Feature, point: Point, sources: Sources) -> str:
    """A title site's name: its appellation, and the nearest address to place it."""
    appellation = str(_props(parcel).get("appellation") or f"Parcel {_props(parcel)['id']}")
    near = sources.addresses.in_envelope(_grown((*point, *point), NEAR_ADDRESS_M)).features
    if not near:
        return appellation
    here = ShapelyPoint(point)
    nearest = min(near, key=lambda f: here.distance(shape(f["geometry"])))
    return f"{appellation}, beside {_props(nearest)['full_address']}"


def _title_parcels(sources: Sources, titles: Sequence[str]) -> tuple[list[Feature], BBox]:
    """Every parcel on ``titles``, and their extent; more than a section refused."""
    parcels = _on_titles(sources.parcels, titles)
    extent = bounds([pt for f in parcels for pt in _ring(f)])
    if len(parcels) > MAX_PARCELS or max(extent[2] - extent[0], extent[3] - extent[1]) > MAX_SIDE_M:
        raise SiteError(
            f"title {', '.join(titles)} is {len(parcels)} parcels over "
            f"{extent[2] - extent[0]:.0f} x {extent[3] - extent[1]:.0f} m: more than a section "
            f"(at most {MAX_PARCELS} parcels within {MAX_SIDE_M:g} m)"
        )
    return parcels, extent


def _frontages_of(title: Title, sources: Sources) -> tuple[Frontage, ...]:
    """Which of the title's edges face a road; the address's own is its street."""
    if title.addressed and title.road_id is None:
        raise SiteError(f"LINZ gives no road for {title.address}: its street can't be named")
    rings = [_ring(f) for f in title.parcels]
    try:
        return fetch_frontages(sources.parcels, sources.roads, rings, title.road_id)
    except LookupError as error:  # LINZ lacks the address's road: no street to name
        raise SiteError(str(error)) from error


def title_parcels(layer: FeatureLayer, parcel: Feature) -> list[Feature]:
    """Every parcel on the record(s) of title ``parcel`` is on, itself included;
    none if it has no title."""
    titles = _titles(parcel)
    return _on_titles(layer, titles) if titles else []


def _on_titles(layer: FeatureLayer, titles: Sequence[str]) -> list[Feature]:
    """Every parcel on any of ``titles``, asked for in one query. More titles
    than a section's parcels (a unit-title development's base) is refused
    before asking: it is more than a section, and each title is a slow,
    unindexed LIKE."""
    if len(titles) > MAX_PARCELS:
        raise SiteError(
            f"{len(titles)} titles are more than a section (at most {MAX_PARCELS} parcels)"
        )
    if not titles:
        return []
    # Each is a title number (TITLE), so the clause holds nothing but them.
    where = " OR ".join(f"titles LIKE '%{title}%'" for title in titles)
    found = {
        int(_props(feature)["id"]): feature
        for feature in layer.where(where).features
        if set(titles) & set(_titles(feature))  # LIKE '%1%' also finds 10 and 21
    }
    return [found[k] for k in sorted(found)]


def _terrain(
    extent: BBox, directory: Path, sources: Sources
) -> tuple[Collection, Collection, TerrainGrid]:
    reach = _grown(extent, TERRAIN_MARGIN_M)
    pairs = lidar_pairs(sources.catalogues.lidar_index(), reach)
    if not pairs:
        raise NoLidar("no LINZ 1 m LiDAR DEM and DSM both cover this site")
    gaps: list[str] = []
    for dem, dsm in pairs:  # newest first: an edge tile can be empty over the site
        for collection, name in ((dem, "dem.tif"), (dsm, "dsm.tif")):
            tiles = cast("list[str]", collection.tiles_for(reach))
            sources.join(tiles, reach, directory / name)
        try:
            grid = read_terrain(str(directory / "dem.tif"), str(directory / "dsm.tif"), extent)
        except ValueError as error:
            gaps.append(f"{dem.title}: {error}")
            continue
        return dem, dsm, grid
    raise NoLidar(f"every LiDAR survey listing this site has gaps over it: {'; '.join(gaps)}")


def _aerial(
    region: str, grid: TerrainGrid, extent: BBox, sources: Sources
) -> tuple[Collection, list[str], bytes]:
    """The best aerial over the LiDAR's ground, and the photo of it to serve
    and survey (``grid.bbox`` at ``PIXEL_M``), as PNG."""
    gaps: list[str] = []
    for collection, tiles in sources.catalogues.aerials_for(region, grid.bbox):
        try:
            pixels = sources.read_aerial(tiles, grid.bbox, PIXEL_M)
        except ValueError as error:  # a listed tile empty over the site: try the next
            gaps.append(f"{collection.title}: {error}")
            continue
        buffer = io.BytesIO()
        Image.fromarray(pixels, "RGB").save(buffer, format="PNG")
        return collection, tiles, buffer.getvalue()
    if gaps:
        raise SiteError(f"every aerial listing this site has gaps over it: {'; '.join(gaps)}")
    raise SiteError(f"no aerial photo in {region} at 0.3 m or finer since 2015 covers it")


def aerial_pixels(png: bytes) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(png)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _grown(extent: BBox, margin_m: float) -> BBox:
    west, south, east, north = extent
    return (
        float(math.floor(west - margin_m)),
        float(math.floor(south - margin_m)),
        float(math.ceil(east + margin_m)),
        float(math.ceil(north + margin_m)),
    )


def _manifest(
    address_id: int | None,  # None: a title site, built from its parcel
    title: Title,
    rasters: tuple[Collection, Collection, Collection],
    aerial_tiles: Sequence[str],
    sources: Sources,
) -> dict[str, Any]:
    dem, dsm, aerial = rasters
    reach = _grown(title.extent, TERRAIN_MARGIN_M)
    open_items = ["What stands on the site: the survey's features wait for the owner's word."]
    if len(title.parcels) > 1:
        open_items.append(
            "Whether the lines between the title's parcels are legal boundaries "
            "(the evaluator reports them as unknown)."
        )
    return {
        "name": title.address,
        "title": ", ".join(title.titles),
        "valuation_number": None,
        "address": {"linz_address_id": address_id, "nztm": list(title.point)},
        "parcels_file": "parcels.geojson",
        "frontages_file": "frontages.geojson",
        "parcel_ids": [int(_props(f)["id"]) for f in title.parcels],
        "extent": {"nztm": list(title.extent)},
        "rasters": {
            "dem": _raster(dem, cast("list[str]", dem.tiles_for(reach)), "dem.tif"),
            "dsm": _raster(dsm, cast("list[str]", dsm.tiles_for(reach)), "dsm.tif"),
            "aerial": _raster(aerial, aerial_tiles, "aerial.png"),
        },
        "vectors": {
            "parcels": _vector("LINZ NZ Primary Parcels", sources.parcels.url),
            "building_outlines": _vector("LINZ NZ Building Outlines", sources.buildings.url),
            "roads": _vector("LINZ NZ Addresses: Roads", sources.roads.url),
        },
        "open_items": open_items,
        "built_at": datetime.now(UTC).isoformat(),
    }


def _raster(collection: Collection, tiles: Sequence[str], asset: str) -> dict[str, Any]:
    return {
        "title": collection.title,
        "collection": collection.url,
        "tiles": list(tiles),
        "asset": asset,
        "resolution_m": collection.gsd_m,
        "capture": {"start": collection.start, "end": collection.end},
        "licence": collection.licence,
        "attribution": ", ".join(collection.providers),
    }


def _vector(title: str, service: str) -> dict[str, str]:
    return {"title": title, "service": service, "licence": "CC-BY-4.0", "attribution": LINZ}


def _survey_meta(aerial: Collection, lidar: list[str]) -> dict[str, Any]:
    """Where the survey's evidence came from: LINZ's own aerial and LiDAR tiles,
    never the server's joined copies."""
    return {
        "model": "sam-3.1",
        "concepts": list(CONCEPTS),
        "aerial": {"title": aerial.title, "captured": [aerial.start, aerial.end]},
        "lidar": lidar,
        "surveyed_at": datetime.now(UTC).isoformat(),
    }


def _parcels_file(title: Title) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "parcel_id": int(_props(f)["id"]),
                    "appellation": str(_props(f).get("appellation") or ""),
                    "survey_area_m2": float(_props(f).get("survey_area") or 0.0),
                },
                "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in _ring(f)]]},
            }
            for f in title.parcels
        ],
    }


def outlines_collection(features: Sequence[Feature]) -> dict[str, Any]:
    """LINZ building outlines as an NZTM FeatureCollection, as LINZ draws them
    (a courtyard building keeps its hole)."""
    return {
        "type": "FeatureCollection",
        "crs": "EPSG:2193",
        "features": [
            {
                "type": "Feature",
                "id": str(_props(f).get("building_id", "")),
                "properties": {"capture_source": _props(f).get("capture_source_name")},
                "geometry": f["geometry"],
            }
            for f in features
            if f.get("geometry")
        ],
    }


def _titles(feature: Feature) -> list[str]:
    raw = str(_props(feature).get("titles") or "")
    return [t.strip() for t in raw.split(",") if _is_title(t.strip())]


def _is_title(value: str) -> bool:
    return re.fullmatch(TITLE, value) is not None


def _holds(feature: Feature, point: ShapelyPoint) -> bool:
    geometry = cast("dict[str, Any] | None", feature.get("geometry"))
    return geometry is not None and shape(geometry).covers(point)


def _ring(feature: Feature) -> Ring:
    geometry = cast("dict[str, Any]", feature["geometry"])
    if geometry.get("type") != "Polygon":
        raise SiteError(f"parcel {_props(feature).get('id')} isn't a simple polygon")
    rings = cast("list[list[list[float]]]", geometry["coordinates"])
    if len(rings) > 1:  # land inside it isn't on the title: never fill it in
        raise SiteError(f"parcel {_props(feature).get('id')} has land within it that isn't its own")
    return tuple((float(x), float(y)) for x, y, *_ in rings[0])


def _props(feature: Feature) -> dict[str, Any]:
    return cast("dict[str, Any]", feature["properties"])


def _write(path: Path, body: dict[str, Any]) -> None:
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(body, indent=1), encoding="utf-8")
    partial.replace(path)
