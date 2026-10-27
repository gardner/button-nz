"""Tests for button_nz.config service endpoints."""

from button_nz.config import ServiceEndpoints, load_basemap_api_key


def test_defaults_point_at_registry_services() -> None:
    endpoints = ServiceEndpoints()
    assert endpoints.buller_property_url.endswith("BDC_Property_Master_Public_View/FeatureServer")
    assert endpoints.linz_addresses_url.endswith("LINZ_NZ_Addresses/FeatureServer")
    assert endpoints.linz_buildings_url.endswith("LINZ_NZ_Building_Outlines/FeatureServer")


def test_default_urls_contain_no_api_key() -> None:
    endpoints = ServiceEndpoints()
    for url in (
        endpoints.buller_property_url,
        endpoints.nelson_property_url,
        endpoints.linz_addresses_url,
        endpoints.linz_buildings_url,
        endpoints.basemaps_tiles_base_url,
    ):
        assert "api=" not in url


def test_wmts_capabilities_url_appends_key() -> None:
    url = ServiceEndpoints().wmts_capabilities_url("NZTM2000Quad", "KEY123")
    assert url == (
        "https://basemaps.linz.govt.nz/v1/tiles/aerial/NZTM2000Quad/WMTSCapabilities.xml?api=KEY123"
    )


def test_aerial_xyz_url_builds_tile_address() -> None:
    url = ServiceEndpoints().aerial_xyz_url(19, 512436, 329889, "KEY123")
    assert url == (
        "https://basemaps.linz.govt.nz/v1/tiles/aerial/WebMercatorQuad/19/512436/329889.webp"
        "?api=KEY123"
    )


def test_from_env_overrides_endpoints() -> None:
    endpoints = ServiceEndpoints.from_env({"LINZ_ADDRESSES_FEATURESERVER_URL": "https://x.example"})
    assert endpoints.linz_addresses_url == "https://x.example"


def test_load_basemap_api_key_reads_env_mapping() -> None:
    assert load_basemap_api_key({"LINZ_BASEMAP_API_KEY": "abc"}) == "abc"
    assert load_basemap_api_key({}) == ""
