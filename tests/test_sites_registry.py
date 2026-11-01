"""Tests for button_nz.sites.registry: sites built from an address or a title."""

import sqlite3
from pathlib import Path

from button_nz.sites.registry import SiteStatus, SiteStore

OLD_SCHEMA = """
CREATE TABLE sites (
    id TEXT PRIMARY KEY,
    address_id INTEGER NOT NULL UNIQUE,
    address TEXT NOT NULL,
    status TEXT NOT NULL,
    step TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE site_builds (site_id TEXT NOT NULL REFERENCES sites (id), requested_at TEXT NOT NULL);
"""


def test_a_site_with_no_address_is_kept_by_its_title(tmp_path: Path) -> None:
    store = SiteStore(tmp_path / "sites.db")
    made = store.create_title(7263035, "Lot 1 DP 428487, beside 17 Munson Street, Reefton")
    assert made.id == "lot-1-dp-428487-beside-17-munson-street-reefton"
    assert (made.address_id, made.parcel_id, made.status) == (None, 7263035, SiteStatus.BUILDING)
    assert store.by_parcel(7263035) == made
    assert store.by_parcel(1) is None


def test_sites_made_before_title_sites_are_kept_when_the_store_opens(tmp_path: Path) -> None:
    path = tmp_path / "sites.db"
    with sqlite3.connect(path) as db:
        db.executescript(OLD_SCHEMA)
        db.execute(
            "INSERT INTO sites (id, address_id, address, status, created_at) VALUES "
            "('7-smith-street-reefton', 42, '7 Smith Street, Reefton', 'ready', '2026-11-01')"
        )
    store = SiteStore(path)
    kept = store.by_address(42)
    assert kept is not None and kept.id == "7-smith-street-reefton" and kept.parcel_id is None
    assert store.create_title(9, "Lot 9 DP 1").parcel_id == 9  # the new column works
