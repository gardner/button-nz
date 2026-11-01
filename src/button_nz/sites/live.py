"""The live sources a server builds sites from: LINZ's national layers, its
STAC catalogues (cached under ``DATA/stac``), SAM 3.1 with the server's key,
and the readers that join LiDAR tiles and cut aerials.

SAM's key is read when a build starts, never at import or start-up, so a
server without one still serves; a build without one fails with the reason.
"""

from collections.abc import Callable
from pathlib import Path

import httpx

from button_nz.api.town import LINZ_PRIMARY_PARCELS
from button_nz.config import ServiceEndpoints
from button_nz.geo.arcgis import FeatureLayer
from button_nz.geo.geometry import BBox
from button_nz.geo.imagery import read_aerial
from button_nz.geo.property import LINZ
from button_nz.sites.build import Sources, outlines_collection
from button_nz.sites.frontages import LINZ_ADDRESS_ROADS
from button_nz.sites.stac import Catalogues
from button_nz.town.lidar import mosaic


class LiveLayers:
    """LINZ's addresses, primary parcels and building outlines, over ``client``."""

    def __init__(self, client: httpx.Client, endpoints: ServiceEndpoints | None = None) -> None:
        found = endpoints or ServiceEndpoints.from_env()
        self.addresses = FeatureLayer(f"{found.linz_addresses_url}/0", "CC-BY-4.0", LINZ, client)
        self.parcels = FeatureLayer(LINZ_PRIMARY_PARCELS, "CC-BY-4.0", LINZ, client)
        self.buildings = FeatureLayer(f"{found.linz_buildings_url}/0", "CC-BY-4.0", LINZ, client)
        self.roads = FeatureLayer(LINZ_ADDRESS_ROADS, "CC-BY-4.0", LINZ, client)

    def outlines(self, bbox: BBox) -> dict[str, object]:
        """The building outlines over ``bbox``, as an NZTM FeatureCollection."""
        return outlines_collection(self.buildings.in_envelope(bbox).features)


def live_sources(layers: LiveLayers, client: httpx.Client, cache: Path) -> Callable[[], Sources]:
    """What each site build reads from, made as the build starts."""
    catalogues = Catalogues(client, cache)

    def sources() -> Sources:
        from button_nz.perception.sam import Segmenter  # needs the key: only when building

        segmenter = Segmenter.from_env()
        return Sources(
            addresses=layers.addresses,
            parcels=layers.parcels,
            buildings=layers.buildings,
            roads=layers.roads,
            catalogues=catalogues,
            segment=segmenter.masks,
            join=mosaic,
            read_aerial=read_aerial,
        )

    return sources
