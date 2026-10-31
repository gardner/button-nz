"""Tests for the town screen's results, report and map."""

import json
from pathlib import Path

from PIL import Image
from shapely import box

from button_nz.town.map import COLOURS, draw_map
from button_nz.town.report import report, summarise, write_results
from button_nz.town.screen import SectionResult


def result(parcel_id: int, area: float, fits: tuple[str, ...] = (), **kw: object) -> SectionResult:
    fields: dict[str, object] = {
        "parcel_id": parcel_id,
        "area_m2": area,
        "buildings": 0,
        "room_m2": 0.0,
        "fits": fits,
        "fits_eaves": fits,
        "clear_room_m2": 0.0,
        "clear": fits,
        "clear_eaves": fits,
    }
    return SectionResult(**(fields | kw))  # pyright: ignore[reportArgumentType]


RESULTS = [
    result(1, 250, ()),
    result(2, 500, ("a", "b"), fits_eaves=("a",), clear=("a",), clear_eaves=()),
    result(3, 800, ("a",), buildings=1),
    result(4, 1200, ("b",), clear=(), clear_eaves=()),
]
META = {
    "commit": "abc1234",
    "envelope": (1.0, 2.0, 3.0, 4.0),
    "outside_zone": 5,
    "other_intent": {"Road": 2},
    "sources": [
        {
            "title": "Parcels",
            "service": "https://example.test/parcels",
            "licence": "CC-BY-4.0",
            "attribution": "Example Council",
            "captured": "2015-12 to 2016-06",
        }
    ],
    "products": {"a": "Supplier A Model A (10 x 5 m)", "b": "Supplier B Model B (12 x 6 m)"},
}


def test_summary_counts_sections_with_room_for_at_least_one_product() -> None:
    counts = summarise(RESULTS)
    assert counts["sections"] == 4
    assert counts["with_buildings"] == 1
    assert counts["fits"] == 3
    assert counts["fits_eaves"] == 3
    assert counts["clear"] == 2
    assert counts["clear_eaves"] == 1
    assert counts["by_product"]["a"] == {"fits": 2, "fits_eaves": 2, "clear": 2, "clear_eaves": 1}


def test_the_report_states_the_counts_sources_and_what_is_not_checked() -> None:
    text = report(RESULTS, META)
    assert "| Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves | 1 | 25% |" in text
    assert "| Room under LINZ outlines, stated dimensions | 3 | 75% |" in text
    assert "abc1234" in text
    assert "Example Council" in text and "CC-BY-4.0" in text
    assert "## What it doesn't check" in text
    assert "Supplier A Model A (10 x 5 m)" in text
    assert "Road: 2" in text


def test_results_are_keyed_by_parcel_id_alone(tmp_path: Path) -> None:
    path = write_results(RESULTS[:2], tmp_path / "results.jsonl")
    lines = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert lines[1]["parcel_id"] == 2
    assert lines[1]["fits"] == ["a", "b"]
    assert not {"appellation", "titles", "address", "valuation"} & lines[1].keys()


def test_the_map_colours_each_section_by_its_result(tmp_path: Path) -> None:
    shapes = {
        1: box(0, 0, 40, 40),
        2: box(60, 0, 100, 40),
        3: box(60, 60, 100, 100),
        4: box(0, 60, 40, 100),
    }
    path = draw_map(RESULTS, shapes, [box(70, 10, 80, 20)], (0, 0, 100, 100), tmp_path / "m.png")
    image = Image.open(path).convert("RGB")
    to_pixel = image.width / 100

    def at(x: float, y: float) -> tuple[int, ...]:
        return image.getpixel((int(x * to_pixel), int((100 - y) * to_pixel)))  # type: ignore[return-value]

    assert at(20, 20) == COLOURS["none"]
    assert at(65, 35) == COLOURS["outlines_only"]  # parcel 2: clear_eaves is empty
    assert at(75, 15) == COLOURS["building"]
    assert at(20, 80) == COLOURS["outlines_only"]
    assert at(80, 80) == COLOURS["clear"]
