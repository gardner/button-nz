"""Service endpoint configuration.

Only public URLs live here. API keys stay in ``.env`` and are appended to
basemap requests at call time. Never hard-code a key in a committed URL.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceEndpoints:
    """Public geospatial service endpoints, overridable via environment."""

    buller_property_url: str = (
        "https://services6.arcgis.com/Whb8vGWSmNkavSpL/arcgis/rest/services/"
        "BDC_Property_Master_Public_View/FeatureServer"
    )
    nelson_property_url: str = (
        "https://www.topofthesouthmaps.co.nz/arcgis/rest/services/"
        "ArcGISOnline_NCC/PropertyBoundariesWithAssess/MapServer"
    )
    linz_addresses_url: str = (
        "https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/"
        "LINZ_NZ_Addresses/FeatureServer"
    )
    linz_buildings_url: str = (
        "https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/"
        "LINZ_NZ_Building_Outlines/FeatureServer"
    )
    basemaps_tiles_base_url: str = "https://basemaps.linz.govt.nz/v1/tiles"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ServiceEndpoints:
        """Build endpoints, applying per-URL environment overrides."""
        source: Mapping[str, str] = os.environ if env is None else env
        defaults = cls()
        return cls(
            buller_property_url=source.get(
                "BULLER_PROPERTY_FEATURESERVER_URL", defaults.buller_property_url
            ),
            nelson_property_url=source.get(
                "NELSON_PROPERTY_MAPSERVER_URL", defaults.nelson_property_url
            ),
            linz_addresses_url=source.get(
                "LINZ_ADDRESSES_FEATURESERVER_URL", defaults.linz_addresses_url
            ),
            linz_buildings_url=source.get(
                "LINZ_BUILDING_OUTLINES_FEATURESERVER_URL", defaults.linz_buildings_url
            ),
            basemaps_tiles_base_url=source.get(
                "LINZ_BASEMAPS_TILES_BASE_URL", defaults.basemaps_tiles_base_url
            ),
        )

    def wmts_capabilities_url(self, grid: str, api_key: str) -> str:
        """Aerial WMTS capabilities URL for ``grid`` (key appended, never stored)."""
        return f"{self.basemaps_tiles_base_url}/aerial/{grid}/WMTSCapabilities.xml?api={api_key}"

    def aerial_xyz_url(self, z: int, x: int, y: int, api_key: str) -> str:
        """Aerial XYZ tile URL in WebMercatorQuad (key appended, never stored)."""
        return (
            f"{self.basemaps_tiles_base_url}/aerial/WebMercatorQuad/{z}/{y}/{x}.webp?api={api_key}"
        )


def load_basemap_api_key(env: Mapping[str, str] | None = None) -> str:
    """Return the LINZ Basemaps key from the environment, or an empty string."""
    source: Mapping[str, str] = os.environ if env is None else env
    return source.get("LINZ_BASEMAP_API_KEY", "")
