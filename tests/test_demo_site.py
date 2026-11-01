"""Tests for button_nz.demo_site, the verified demo-site manifest."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from button_nz.demo_site import DEMO_SITE_DIR, contains, load_demo_site


def test_loads_the_verified_site() -> None:
    site = load_demo_site()
    assert site.name == "35 Victory Street, Reefton"
    assert site.title == "354613"
    assert [p.parcel_id for p in site.parcels] == [3652040, 3621992, 3615590, 3625049]
    assert site.parcels[3].appellation == "Section 1336 TN OF Reefton"
    assert set(site.rasters) == {"dem", "dsm", "aerial", "aerial_rural"}
    assert site.rasters["dem"].resolution_m == 1.0
    assert site.open_items


def test_the_address_point_is_in_section_701() -> None:
    site = load_demo_site()
    holding = [p.appellation for p in site.parcels if contains(p.ring, site.address_nztm)]
    assert holding == ["Section 701 TN OF Reefton"]


def test_contains() -> None:
    square = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    assert contains(square, (5.0, 5.0))
    assert not contains(square, (15.0, 5.0))
    assert not contains(square, (5.0, -1.0))


@pytest.fixture
def site_dir(tmp_path: Path) -> Path:
    copy = tmp_path / "demo-site"
    shutil.copytree(DEMO_SITE_DIR, copy)
    return copy


def _edit(site_dir: Path, keys: tuple[str | int, ...], value: object) -> None:
    """Set the manifest value at ``keys`` to ``value``."""
    path = site_dir / "site.json"
    manifest: Any = json.loads(path.read_text(encoding="utf-8"))
    node = manifest
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_parcel_ids_must_match_the_geojson(site_dir: Path) -> None:
    _edit(site_dir, ("parcel_ids",), [3652040, 3621992, 3615590])
    with pytest.raises(ValueError, match="parcel"):
        load_demo_site(site_dir)


def test_extent_must_be_the_parcels_bounding_box(site_dir: Path) -> None:
    _edit(site_dir, ("extent", "nztm", 0), 1505900.0)
    with pytest.raises(ValueError, match="extent"):
        load_demo_site(site_dir)


def test_address_must_fall_in_a_parcel(site_dir: Path) -> None:
    _edit(site_dir, ("address", "nztm"), [1505000.0, 5336000.0])
    with pytest.raises(ValueError, match="address"):
        load_demo_site(site_dir)


def test_every_raster_tile_must_cover_the_site(site_dir: Path) -> None:
    """Swapping tile and asset together for the tile to the south is caught."""
    south = "BS21_1000_4830"
    collection = "https://nz-imagery.s3.ap-southeast-2.amazonaws.com/west-coast/buller_2024-2025_0.075m/rgb/2193"
    _edit(site_dir, ("rasters", "aerial", "tile"), south)
    _edit(site_dir, ("rasters", "aerial", "asset"), f"{collection}/{south}.tiff")
    with pytest.raises(ValueError, match="aerial: tile BS21_1000_4830 does not cover"):
        load_demo_site(site_dir)


def test_a_site_moved_off_its_tiles_is_rejected(site_dir: Path) -> None:
    """Moving the parcels, extent and address together must not slip past the tiles."""
    parcels_path = site_dir / "parcels.geojson"
    parcels: Any = json.loads(parcels_path.read_text(encoding="utf-8"))
    for feature in parcels["features"]:
        ring = feature["geometry"]["coordinates"][0]
        feature["geometry"]["coordinates"][0] = [[x + 1000.0, y] for x, y in ring]
    parcels_path.write_text(json.dumps(parcels), encoding="utf-8")
    _edit(site_dir, ("extent", "nztm"), [1506926.13, 5336777.48, 1506969.74, 5336822.22])
    _edit(site_dir, ("address", "nztm"), [1506941.6, 5336793.7])
    with pytest.raises(ValueError, match="does not cover"):
        load_demo_site(site_dir)


def test_a_raster_asset_must_be_its_tile(site_dir: Path) -> None:
    asset = "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0504.tiff"
    _edit(site_dir, ("rasters", "dem", "asset"), asset)
    with pytest.raises(ValueError, match="dem"):
        load_demo_site(site_dir)


def test_a_raster_asset_must_be_in_its_collection(site_dir: Path) -> None:
    asset = "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dsm_1m/2193/BS21_10000_0503.tiff"
    _edit(site_dir, ("rasters", "dem", "asset"), asset)
    with pytest.raises(ValueError, match="dem"):
        load_demo_site(site_dir)


def test_capture_must_start_before_it_ends(site_dir: Path) -> None:
    _edit(site_dir, ("rasters", "dsm", "capture", "end"), "2019-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="dsm"):
        load_demo_site(site_dir)


def _as_built(site_dir: Path) -> None:
    """The demo manifest as the site builder writes one: rasters joined from
    their tiles into local files, and no valuation number."""
    path = site_dir / "site.json"
    manifest: Any = json.loads(path.read_text(encoding="utf-8"))
    manifest["valuation_number"] = None
    for key in ("dem", "dsm", "aerial", "aerial_rural"):
        raster = manifest["rasters"][key]
        raster["tiles"] = [raster.pop("asset")]
        raster.pop("tile")
        raster["asset"] = f"{key}.tif"
        (site_dir / f"{key}.tif").write_bytes(b"joined")
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_a_built_site_reads_its_local_rasters_and_lists_their_tiles(site_dir: Path) -> None:
    _as_built(site_dir)
    site = load_demo_site(site_dir)
    assert site.valuation_number is None
    dem = site.rasters["dem"]
    assert dem.asset == str(site_dir / "dem.tif")
    assert dem.tile is None
    assert dem.tiles == (
        "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0503.tiff",
    )


def test_a_built_raster_must_exist_beside_the_manifest(site_dir: Path) -> None:
    _as_built(site_dir)
    (site_dir / "dsm.tif").unlink()
    with pytest.raises(ValueError, match="dsm"):
        load_demo_site(site_dir)


def test_a_built_rasters_tiles_must_cover_the_site(site_dir: Path) -> None:
    _as_built(site_dir)
    north = "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0403.tiff"
    _edit(site_dir, ("rasters", "dem", "tiles"), [north])
    with pytest.raises(ValueError, match="dem: its tiles don't cover"):
        load_demo_site(site_dir)
