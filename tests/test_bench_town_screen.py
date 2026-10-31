"""Tests for the town screen's command: its options, and screening a whole
(synthetic) town against its outlines and LiDAR."""

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from shapely import box

from button_nz.bench.town_screen import parse_options, screen_town, sources
from button_nz.geo.arcgis import FeatureSet, Provenance
from button_nz.geo.terrain import TerrainGrid
from button_nz.town.sources import REEFTON, Section, Selection, TownData
from test_town_screen import prefab


def feature_set(features: tuple[dict[str, Any], ...] = ()) -> FeatureSet:
    when = datetime(2026, 10, 31, tzinfo=UTC)
    return FeatureSet(features, Provenance("https://example.test/layer", {}, when, "", ""))


def town(sections: list[Section], buildings: list[Any], outlines: FeatureSet) -> TownData:
    selection = Selection(tuple(sections), 0, {})
    return TownData(selection, tuple(buildings), feature_set(), feature_set(), outlines)


def test_the_envelope_defaults_to_reefton(tmp_path: Any) -> None:
    options = parse_options([str(tmp_path)])
    assert options.envelope == REEFTON


def test_a_reversed_envelope_is_refused(tmp_path: Any) -> None:
    with pytest.raises(SystemExit):
        parse_options([str(tmp_path), "--envelope", "10,0,0,10"])


def test_each_section_meets_its_own_buildings_and_lidar() -> None:
    open_section = Section(1, box(0, 0, 20, 20))
    built = Section(2, box(30, 0, 50, 20))
    house = box(34, 4, 46, 16)  # leaves no room on section 2
    ndsm = np.zeros((40, 60))
    ndsm[20:24, 8:12] = 6.0  # a tree in section 1's middle (rows from the north edge)
    grid = TerrainGrid((-5, -10, 55, 30), 1.0, np.zeros_like(ndsm), ndsm, ())
    results = screen_town(
        town([open_section, built], [house], feature_set()), grid, [prefab("p", 6, 4)]
    )
    assert [r.parcel_id for r in results] == [1, 2]
    assert results[0].fits == ("p",) and results[0].buildings == 0
    assert results[0].clear_room_m2 < results[0].room_m2
    assert results[1].buildings == 1 and results[1].fits == ()


def test_the_outlines_capture_dates_come_from_the_outlines() -> None:
    def outline(start: str, end: str) -> dict[str, Any]:
        def ms(day: str) -> int:
            return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)

        return {"properties": {"capture_source_from": ms(start), "capture_source_to": ms(end)}}

    found = feature_set((outline("2015-12-26", "2016-03-01"), outline("2016-01-01", "2016-06-01")))
    listed = sources(town([], [], found), ["https://example.test/dem.tiff"])
    by_title = {s["title"]: s for s in listed}
    dates = by_title["LINZ NZ Building Outlines"]["captured"]
    assert dates == "Captured from aerial photos of 2015-12-26 to 2016-06-01"
    assert "no licence stated" in by_title["Buller District Council zones (Residential)"]["licence"]
