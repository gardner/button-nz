"""Add frontages to sites built before they were found.

    uv run python -m button_nz.sites.backfill SITE_DIR [SITE_DIR ...]

Each site's address is looked up in LINZ for its road, its title's frontages
are found as a new build would find them (``sites.frontages``), and its record
gains ``frontages.geojson``. The record must still load afterwards; if it
doesn't, it is put back as it was.
"""

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from button_nz.demo_site import load_demo_site
from button_nz.geo.arcgis import FeatureLayer
from button_nz.geo.property import find_address
from button_nz.sites.frontages import fetch_frontages, to_collection

FRONTAGES_FILE = "frontages.geojson"
ROADS_TITLE = "LINZ NZ Addresses: Roads"


def add_frontages(
    directory: Path, addresses: FeatureLayer, parcels: FeatureLayer, roads: FeatureLayer
) -> None:
    """Find and record the frontages of the site in ``directory``."""
    record = directory / "site.json"
    before = record.read_text(encoding="utf-8")
    manifest: dict[str, Any] = json.loads(before)
    site = load_demo_site(directory)
    address = find_address(addresses, int(manifest["address"]["linz_address_id"])).value
    if address.road_id is None:
        raise ValueError(f"LINZ gives no road for {address.full_address}")
    rings = [parcel.ring for parcel in site.parcels]
    found = fetch_frontages(parcels, roads, rings, address.road_id)
    (directory / FRONTAGES_FILE).write_text(json.dumps(to_collection(found)), encoding="utf-8")
    manifest["frontages_file"] = FRONTAGES_FILE
    manifest["vectors"]["roads"] = {
        "title": ROADS_TITLE,
        "service": roads.url,
        "licence": roads.licence,
        "attribution": roads.attribution,
    }
    record.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    try:
        load_demo_site(directory)
    except ValueError, KeyError:
        record.write_text(before, encoding="utf-8")
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Add frontages to sites built before them.")
    parser.add_argument("sites", nargs="+", type=Path)
    args = parser.parse_args(argv)
    from button_nz.sites.live import LiveLayers  # the live LINZ services

    layers = LiveLayers(httpx.Client(timeout=60.0, follow_redirects=True))
    for directory in args.sites:
        add_frontages(directory, layers.addresses, layers.parcels, layers.roads)
        print(f"{directory}: frontages added")


if __name__ == "__main__":
    main()
