"""Tests for button_nz.sites.backfill: frontages added to a site built before them."""

import json
import shutil
from pathlib import Path
from typing import Any

from button_nz.demo_site import DEMO_SITE_DIR, load_demo_site
from button_nz.sites.backfill import add_frontages
from test_sites_build import layers


def test_a_site_built_before_frontages_gets_them_and_still_loads(tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(DEMO_SITE_DIR, site)
    manifest = json.loads((site / "site.json").read_text(encoding="utf-8"))
    manifest.pop("frontages_file", None)  # as built before frontages
    manifest["address"]["linz_address_id"] = 7  # the fake LINZ's address, on road 99
    (site / "site.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert load_demo_site(site).frontages is None
    found = layers([])
    add_frontages(
        site,
        found["LINZ_NZ_Addresses"],
        found["LINZ_NZ_Primary_Parcels"],
        found["LINZ_NZ_Addresses_Roads"],
    )
    loaded = load_demo_site(site)
    assert loaded.frontages is not None  # known now, whatever they are
    assert loaded.vectors["roads"].title == "LINZ NZ Addresses: Roads"


def test_the_record_is_replaced_whole_never_written_in_place(
    tmp_path: Path, monkeypatch: Any
) -> None:
    site = tmp_path / "site"
    shutil.copytree(DEMO_SITE_DIR, site)
    before = (site / "site.json").read_text(encoding="utf-8")
    real = Path.write_text

    def failing(self: Path, text: str, **kwargs: Any) -> int:
        if self.name == "site.json":  # an in-place write could stop halfway
            raise OSError("disk full")
        return real(self, text, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing)
    found = layers([])
    add_frontages(
        site,
        found["LINZ_NZ_Addresses"],
        found["LINZ_NZ_Primary_Parcels"],
        found["LINZ_NZ_Addresses_Roads"],
    )
    monkeypatch.undo()
    assert (site / "site.json").read_text(encoding="utf-8") != before  # replaced, whole
    assert load_demo_site(site).frontages is not None
