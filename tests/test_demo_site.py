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
    _edit(site_dir, ("rasters", "aerial", "tile_bbox_wgs84", 0), 171.9)
    with pytest.raises(ValueError, match="aerial"):
        load_demo_site(site_dir)


def test_capture_must_start_before_it_ends(site_dir: Path) -> None:
    _edit(site_dir, ("rasters", "dsm", "capture", "end"), "2019-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="dsm"):
        load_demo_site(site_dir)
