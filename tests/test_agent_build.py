"""Tests for button_nz.agent.build: a spec built as a Dwelling the evaluator
measures as the spec says. The geometry is pure Python, so the evaluator's
own measurement (``parse_measurements``) runs here without Blender; the
Blender build of the same script is in test_build_blender.py."""

import json
import math
from typing import Any

import numpy as np
import pytest
from shapely import Polygon

from button_nz.agent.build import (
    DECK_M,
    FASCIA_M,
    FLOOR_M,
    WALL_M,
    check,
    dwelling,
    height_above_floor,
    spec_to_script,
    steepest_pitch,
)
from button_nz.agent.offers import Offer, Offers
from button_nz.agent.proposal import parse_measurements, to_proposal
from button_nz.agent.spec import DesignSpec, SpecError, parse_spec
from button_nz.evaluation import Report, SiteContext, Status, evaluate
from button_nz.evaluation.checks import MAX_HEIGHT_ABOVE_FLOOR_M
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0), (0.0, 0.0))
FRAME = LocalFrame(origin=(20.0, 15.0))
GROUND = 100.0  # flat; the datum is 0, so scene z is NZVD2016
OFFER = Offer(1, (0.0, 0.0), 30.0, 10.0, 7.0, (GROUND, GROUND + 1.0), "centre (0.00, 0.00)")
OFFERS = Offers((OFFER,), (), 0.6)
ROOFS: list[dict[str, Any]] = [
    {"form": "gable", "pitch_deg": 15},
    {"form": "hip", "pitch_deg": 15},
    {"form": "skillion", "pitch_deg": 7, "high_side": "NW"},
    {"form": "flat", "pitch_deg": 0},
]


def _spec(**changes: Any) -> DesignSpec:
    base: dict[str, Any] = {
        "placement": 1,
        "floor_z_m": GROUND + 0.3,
        "roof": ROOFS[0],
        "eaves_m": 0.6,
    }
    return parse_spec(json.dumps(base | changes))


def _site() -> SiteContext:
    dem = np.full((30, 40), GROUND)
    grid = TerrainGrid((0.0, 0.0, 40.0, 30.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    return SiteContext(parcels=(PARCEL,), terrain=grid)


def _measured(spec: DesignSpec) -> tuple[Report, Any]:
    built = dwelling(spec, OFFER)
    raw = {"triangles": built.triangles(), "floor_area_m2": built.floor_area_m2, "storeys": 1}
    proposal = to_proposal(parse_measurements(raw), FRAME, 0.0)
    return evaluate(proposal, _site()), proposal


def _expected_height(spec: DesignSpec) -> float:
    pitch = math.tan(math.radians(spec.roof.pitch_deg))
    run = {"gable": 3.5 + 0.6, "hip": 3.5 + 0.6, "skillion": 7.0 + 1.2, "flat": 0.0}
    return FLOOR_M + spec.wall_height_m + FASCIA_M + run[spec.roof.form] * pitch


@pytest.mark.parametrize("roof", ROOFS, ids=[r["form"] for r in ROOFS])
@pytest.mark.parametrize("deck", [None, {"side": "SE", "depth_m": 2.0}], ids=["bare", "deck"])
def test_every_roof_and_deck_is_measured_as_the_spec_says(
    roof: dict[str, Any], deck: dict[str, Any] | None
) -> None:
    spec = _spec(roof=roof, deck=deck)
    report, proposal = _measured(spec)
    statuses = {c.name: c.status for c in report.checks}
    assert report.status is not Status.FAIL, [c.detail for c in report.checks]
    assert statuses["height"] is statuses["floor_level"] is statuses["floor_area"] is Status.PASS
    assert proposal.floor_level_m == pytest.approx(spec.floor_z_m)
    assert proposal.height_above_floor_m == pytest.approx(_expected_height(spec))
    assert height_above_floor(spec, OFFER) == pytest.approx(_expected_height(spec))
    walls, outline = Polygon(proposal.footprint), Polygon(proposal.outline)
    assert walls.area == pytest.approx(70.0, abs=1e-6)
    eaves = 11.2 * 8.2
    deck_beyond_eaves = 0.0 if deck is None else 10.0 * (2.0 - 0.6)  # beside a long wall
    assert outline.area == pytest.approx(eaves + deck_beyond_eaves, abs=1e-6)
    assert proposal.floor_area_m2 == pytest.approx((10 - 2 * WALL_M) * (7 - 2 * WALL_M))
    assert proposal.storeys == 1


def test_the_walls_stand_where_the_offer_says() -> None:
    _, proposal = _measured(_spec())
    walls = Polygon(FRAME.to_local(p) for p in proposal.footprint)
    a = math.radians(30.0)
    assert walls.centroid.x == pytest.approx(0.0) and walls.centroid.y == pytest.approx(0.0)
    along = walls.exterior.coords[1][0] - walls.exterior.coords[0][0]
    assert along != 0.0
    expected = {round(math.degrees(math.atan2(math.sin(a), math.cos(a))) % 180, 6)}
    edges = list(walls.exterior.coords)
    angles = {
        round(math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180, 6)
        for (x0, y0), (x1, y1) in zip(edges, edges[1:], strict=False)
        if math.hypot(x1 - x0, y1 - y0) > 9.0
    }
    assert angles == expected


def test_the_deck_is_a_thin_slab_level_with_the_floor() -> None:
    spec = _spec(deck={"side": "NE", "depth_m": 2.5, "width_m": 4.0})
    deck = dwelling(spec, OFFER).solids[-1]
    heights = {round(z, 9) for _, _, z in deck.vertices}
    floor_top = spec.floor_z_m + FLOOR_M
    assert heights == {round(floor_top - DECK_M, 9), round(floor_top, 9)}
    assert min(heights) > spec.floor_z_m  # nothing below the floor's underside


def test_the_offers_sides_name_the_compass_point_each_wall_faces() -> None:
    assert set(OFFER.sides()) == {"NW", "NE", "SE", "SW"}  # long walls at 30°
    square = Offer(1, (0.0, 0.0), 0.0, 10.0, 7.0, (0.0, 1.0), "")
    assert square.sides() == {
        "N": (0.0, 1.0),
        "E": (1.0, 0.0),
        "S": (0.0, -1.0),
        "W": (-1.0, 0.0),
    }


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"placement": 2}, "placement 2"),
        ({"floor_z_m": GROUND - 0.1}, "floor"),
        ({"floor_z_m": GROUND + 1.1}, "floor"),
        ({"deck": {"side": "N", "depth_m": 2.0}}, "side N"),
        ({"deck": {"side": "NE", "depth_m": 2.0, "width_m": 11.0}}, "width"),
        ({"roof": {"form": "skillion", "pitch_deg": 7, "high_side": "E"}}, "side E"),
        ({"openings": [{"side": "S", "windows": 1}]}, "side S"),
        ({"roof": {"form": "gable", "pitch_deg": 30}}, "4 m"),
    ],
)
def test_a_spec_its_placement_cant_hold_is_refused_before_blender(
    changes: dict[str, Any], says: str
) -> None:
    with pytest.raises(SpecError, match=says):
        check(_spec(**changes), OFFERS)


def test_a_spec_that_fits_is_checked_to_its_offer() -> None:
    assert check(_spec(), OFFERS) is OFFER


def test_the_steepest_pitch_reaches_the_height_limit() -> None:
    for form, high in (("gable", None), ("skillion", "NW")):
        pitch = steepest_pitch(OFFER, form, wall_height_m=2.4, eaves_m=0.6)
        roof = {"form": form, "pitch_deg": round(pitch, 6)}
        roof |= {"high_side": high} if high else {}
        height = height_above_floor(_spec(roof=roof), OFFER)
        assert height == pytest.approx(MAX_HEIGHT_ABOVE_FLOOR_M, abs=1e-5)


def test_the_script_is_python_that_builds_the_dwelling_and_says_its_spec() -> None:
    spec = _spec(deck={"side": "SE", "depth_m": 2.0})
    script = spec_to_script(spec, OFFER)
    compile(script, "design.py", "exec")
    assert '"Dwelling"' in script and 'dwelling["storeys"] = 1' in script
    assert spec.model_dump_json(exclude_defaults=True) in script.splitlines()[1]
