"""Tests for button_nz.agent.spec: the design Muse proposes, as parameters."""

import json
from typing import Any

import pytest

from button_nz.agent.placement import PROMPT_EAVES_M
from button_nz.agent.spec import DesignSpec, SpecError, parse_spec, spec_tool

GABLE: dict[str, Any] = {
    "placement": 1,
    "floor_z_m": 0.3,
    "roof": {"form": "gable", "pitch_deg": 15},
    "eaves_m": 0.6,
}


def _parse(**changes: Any) -> DesignSpec:
    return parse_spec(json.dumps(GABLE | changes))


def test_a_spec_parses_with_its_defaults() -> None:
    spec = _parse()
    assert spec.placement == 1
    assert spec.floor_z_m == 0.3
    assert spec.wall_height_m == 2.4
    assert spec.roof.form == "gable" and spec.roof.pitch_deg == 15.0
    assert spec.deck is None and spec.openings == []


def test_a_deck_and_openings_parse() -> None:
    spec = _parse(
        deck={"side": "N", "depth_m": 2.4},
        openings=[{"side": "N", "windows": 3, "doors": 1}, {"side": "S", "windows": 2}],
    )
    assert spec.deck is not None and spec.deck.side == "N" and spec.deck.width_m is None
    assert [(o.side, o.windows, o.doors) for o in spec.openings] == [("N", 3, 1), ("S", 2, 0)]


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"eaves_m": PROMPT_EAVES_M + 0.1}, "eaves_m"),
        ({"wall_height_m": 3.5}, "wall_height_m"),
        ({"wall_height_m": 1.8}, "wall_height_m"),
        ({"placement": 0}, "placement"),
        ({"placement": "1"}, "placement"),  # strict: no strings for numbers
        ({"colour": "red"}, "colour"),  # nothing the builder doesn't use
        ({"roof": {"form": "dome", "pitch_deg": 20}}, "form"),
        ({"roof": {"form": "gable", "pitch_deg": 50}}, "pitch"),
        ({"roof": {"form": "hip", "pitch_deg": 5}}, "pitch"),
        ({"roof": {"form": "flat", "pitch_deg": 3}}, "pitch"),
        ({"roof": {"form": "skillion", "pitch_deg": 10}}, "high_side"),
        ({"roof": {"form": "gable", "pitch_deg": 20, "high_side": "N"}}, "high_side"),
        ({"deck": {"side": "N", "depth_m": 4.0}}, "depth_m"),
        ({"deck": {"side": "up", "depth_m": 2.0}}, "side"),
        ({"openings": [{"side": "N", "windows": 1}, {"side": "N", "doors": 1}]}, "once"),
        ({"openings": [{"side": "N", "doors": 5}]}, "doors"),
    ],
)
def test_a_spec_out_of_range_is_refused_with_why(changes: dict[str, Any], says: str) -> None:
    with pytest.raises(SpecError, match=says):
        _parse(**changes)


def test_every_roof_form_parses_in_its_range() -> None:
    for roof in (
        {"form": "gable", "pitch_deg": 10},
        {"form": "hip", "pitch_deg": 45},
        {"form": "skillion", "pitch_deg": 3, "high_side": "SW"},
        {"form": "flat", "pitch_deg": 0},
    ):
        assert _parse(roof=roof).roof.form == roof["form"]


def test_malformed_json_is_a_spec_error() -> None:
    with pytest.raises(SpecError, match="JSON"):
        parse_spec("{not json")


def test_the_tool_offers_the_specs_schema_without_references() -> None:
    tool = spec_tool()
    assert tool["function"]["name"] == "propose_design"
    parameters = tool["function"]["parameters"]
    assert set(parameters["required"]) == {"placement", "floor_z_m", "roof", "eaves_m"}
    assert "$ref" not in json.dumps(parameters) and "$defs" not in parameters
    roof = parameters["properties"]["roof"]
    assert roof["properties"]["form"]["enum"] == ["gable", "hip", "skillion", "flat"]
