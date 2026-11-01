"""Which of LINZ's national LiDAR and aerial collections cover a site.

LINZ publishes its elevation and imagery as STAC catalogues on public S3. A
collection lists its tiles by name on LINZ's tile grid (``geo.tiles``), so a
site is covered when every tile its bounding box touches is in the
collection: no tile needs fetching to know.

- **LiDAR:** every 1 m DEM and DSM collection is indexed once (about 200
  collections) and cached. A site uses the newest survey whose DEM *and* DSM
  both cover it.
- **Aerials:** there are hundreds, some with tens of thousands of tiles, so
  only the LiDAR's region is looked at: its recent collections at 0.3 m or
  finer, preferring 12.5 cm or finer (what the survey reads at), then the
  newest. Each collection fetched is cached.
"""

import json
import re
from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import httpx

from button_nz.geo.geometry import BBox
from button_nz.geo.tiles import tiles_covering

ELEVATION = "https://nz-elevation.s3.ap-southeast-2.amazonaws.com"
IMAGERY = "https://nz-imagery.s3.ap-southeast-2.amazonaws.com"
LIDAR_KINDS = ("dem_1m", "dsm_1m")
COMPOSITE = "./new-zealand/"
FINEST_USEFUL_M = 0.125  # the survey reads the aerial at this; finer is no better
COARSEST_M = 0.3
OLDEST_YEAR = 2015
TILE_NAME = re.compile(r"\./([A-Z]{2}\d{2}_(\d+)_(?:\d{4}|\d{6}))\.json")  # 1:500 has 6 digits
SLUG = re.compile(r"_(\d{4})(?:-(\d{4}))?_(\d+(?:\.\d+)?)m/rgb/2193/collection\.json$")


@dataclass(frozen=True)
class Collection:
    url: str  # its collection.json
    title: str
    region: str
    gsd_m: float
    start: str  # ISO 8601
    end: str
    licence: str
    providers: tuple[str, ...]
    scale: int  # of its tiles on LINZ's grid
    tiles: tuple[str, ...]

    def tiles_for(self, bbox: BBox) -> list[str] | None:
        """The asset URLs of the tiles covering ``bbox`` (NZTM), or None if
        any of them isn't in this collection."""
        names = tiles_covering(bbox, self.scale)
        held = set(self.tiles)
        if not names or any(n not in held for n in names):
            return None
        base = self.url.rsplit("/", 1)[0]
        return [f"{base}/{name}.tiff" for name in names]

    @property
    def survey(self) -> str:
        """The capture the collection belongs to: its DEM and DSM share it."""
        return self.url.rsplit("/", 3)[0]


def parse_collection(url: str, body: dict[str, Any]) -> Collection:
    """A collection from its ``collection.json``."""
    names = [TILE_NAME.fullmatch(str(link["href"])) for link in body.get("links", [])]
    tiles = sorted(m.group(1) for m in names if m)
    scales = {int(m.group(2)) for m in names if m}
    if len(scales) != 1:
        raise ValueError(f"{url}: tiles at {len(scales)} scales, not one")
    interval = cast("list[list[str]]", body["extent"]["temporal"]["interval"])[0]
    providers = cast("list[dict[str, Any]]", body.get("providers", []))
    return Collection(
        url=url,
        title=str(body["title"]),
        region=str(body.get("linz:region", "")),
        gsd_m=float(body["gsd"]),
        start=str(interval[0]),
        end=str(interval[1]),
        licence=str(body["license"]),
        providers=tuple(str(p["name"]) for p in providers),
        scale=scales.pop(),
        tiles=tuple(tiles),
    )


def lidar_pairs(index: Iterable[Collection], bbox: BBox) -> list[tuple[Collection, Collection]]:
    """Every survey's DEM and DSM collections whose tiles both cover ``bbox``,
    newest first. A survey's edge tile can still be empty over the site, so a
    builder tries them in turn."""
    by_survey: dict[str, dict[str, Collection]] = {}
    for collection in index:
        kind = next((k for k in LIDAR_KINDS if f"/{k}/" in collection.url), None)
        if kind and collection.tiles_for(bbox) is not None:
            by_survey.setdefault(collection.survey, {})[kind] = collection
    pairs = [(s["dem_1m"], s["dsm_1m"]) for s in by_survey.values() if len(s) == 2]
    return sorted(pairs, key=lambda pair: pair[0].end, reverse=True)


def choose_lidar(index: Iterable[Collection], bbox: BBox) -> tuple[Collection, Collection] | None:
    """The newest survey's DEM and DSM collections that both cover ``bbox``."""
    pairs = lidar_pairs(index, bbox)
    return pairs[0] if pairs else None


def aerial_candidates(catalog_links: Sequence[str], region: str) -> list[str]:
    """The region's recent aerial collections at 0.3 m or finer, best first:
    fine enough for the survey, then the newest, then the finest."""
    ranked: list[tuple[tuple[bool, int, float], str]] = []
    for href in catalog_links:
        found = SLUG.search(href)
        if not href.startswith(f"./{region}/") or found is None:
            continue
        end, gsd = int(found.group(2) or found.group(1)), float(found.group(3))
        if gsd <= COARSEST_M and end >= OLDEST_YEAR:
            ranked.append(((gsd > FINEST_USEFUL_M, -end, gsd), href))
    return [f"{IMAGERY}/{href.removeprefix('./')}" for _, href in sorted(ranked)]


class Catalogues:
    """LINZ's catalogues, fetched with ``client`` and cached under ``cache``."""

    def __init__(self, client: httpx.Client, cache: Path) -> None:
        self.client, self.cache = client, cache

    def lidar_index(self) -> list[Collection]:
        path = self.cache / "elevation.json"
        if path.is_file():
            return [_collection(raw) for raw in json.loads(path.read_text(encoding="utf-8"))]
        links = self._children(ELEVATION)
        # Not ./new-zealand/: national mosaics of many captures (2008 to now),
        # whose dates would say nothing about a site's own.
        urls = [
            f"{ELEVATION}/{h.removeprefix('./')}"
            for h in links
            if any(f"/{k}/2193/" in h for k in LIDAR_KINDS) and not h.startswith(COMPOSITE)
        ]
        with ThreadPoolExecutor(max_workers=16) as pool:
            index = list(pool.map(self.collection, urls))
        self.cache.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(c) for c in index]), encoding="utf-8")
        return index

    def aerials_for(self, region: str, bbox: BBox) -> Iterator[tuple[Collection, list[str]]]:
        """Each aerial collection in ``region`` whose tiles cover ``bbox``, best
        first, with its tiles. A tile can still be empty over the site, so a
        builder tries them in turn."""
        for url in aerial_candidates(self._children(IMAGERY), region):
            collection = self._cached(url)
            tiles = collection.tiles_for(bbox)
            if tiles is not None:
                yield collection, tiles

    def collection(self, url: str) -> Collection:
        return parse_collection(url, self._json(url))

    def _cached(self, url: str) -> Collection:
        path = self.cache / "imagery" / (url.removeprefix(f"{IMAGERY}/").replace("/", "__"))
        if path.is_file():
            return _collection(json.loads(path.read_text(encoding="utf-8")))
        collection = self.collection(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(collection)), encoding="utf-8")
        return collection

    def _children(self, root: str) -> list[str]:
        links = cast("list[dict[str, Any]]", self._json(f"{root}/catalog.json")["links"])
        return [str(link["href"]) for link in links if link.get("rel") == "child"]

    def _json(self, url: str) -> dict[str, Any]:
        response = self.client.get(url, timeout=60.0)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())


def _collection(raw: dict[str, Any]) -> Collection:
    """A collection from its cached record (``asdict``)."""
    return Collection(
        url=str(raw["url"]),
        title=str(raw["title"]),
        region=str(raw["region"]),
        gsd_m=float(raw["gsd_m"]),
        start=str(raw["start"]),
        end=str(raw["end"]),
        licence=str(raw["licence"]),
        providers=tuple(str(p) for p in raw["providers"]),
        scale=int(raw["scale"]),
        tiles=tuple(str(t) for t in raw["tiles"]),
    )
