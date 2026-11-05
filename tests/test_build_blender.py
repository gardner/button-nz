"""Every roof form, with and without a deck, built by real sandboxed Blender
from its spec and measured by the evaluator as the spec says. Run with
`pytest -m blender`."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from shapely import Polygon

from button_nz.agent.build import dwelling, height_above_floor, spec_to_script
from button_nz.agent.offers import Offer
from button_nz.agent.proposal import parse_measurements, to_proposal
from button_nz.agent.spec import parse_spec
from button_nz.blender_worker.run import run_design
from button_nz.blender_worker.scene_input import scene_input
from button_nz.evaluation import Footprint, Proposal, SiteContext, Status, evaluate
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid

pytestmark = pytest.mark.blender

PARCEL: Ring = ((0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0), (0.0, 0.0))
ROOFS: list[dict[str, Any]] = [
    {"form": "gable", "pitch_deg": 15},
    {"form": "hip", "pitch_deg": 15},
    {"form": "skillion", "pitch_deg": 7, "high_side": "NW"},
    {"form": "flat", "pitch_deg": 0},
]
TURNED = Offer(1, (0.0, 0.0), 30.0, 10.0, 7.0, (0.0, 0.0), "")  # its walls face NW, NE, SE, SW


@pytest.mark.parametrize("roof", ROOFS, ids=[r["form"] for r in ROOFS])
@pytest.mark.parametrize("deck", [None, {"side": "SE", "depth_m": 2.0}], ids=["bare", "deck"])
def test_blender_builds_the_spec_the_evaluator_measures(
    roof: dict[str, Any], deck: dict[str, Any] | None, tmp_path: Path
) -> None:
    _built_as_specified(roof, deck, TURNED, tmp_path)


def test_a_square_products_hip_roof_is_a_pyramid(tmp_path: Path) -> None:
    square = Offer(1, (2.0, -3.0), 0.0, 6.0, 6.0, (0.0, 0.0), "")
    roof = {"form": "hip", "pitch_deg": 15}
    proposal = _built_as_specified(roof, None, square, tmp_path, Footprint("Cube", 6.0, 6.0))
    assert Polygon(proposal.footprint).area == pytest.approx(36.0, abs=1e-3)


def _built_as_specified(
    roof: dict[str, Any],
    deck: dict[str, Any] | None,
    offer: Offer,
    tmp_path: Path,
    product: Footprint | None = None,
) -> Proposal:
    dem = np.full((30, 40), 100.0)
    grid = TerrainGrid((0.0, 0.0, 40.0, 30.0), 1.0, dem, np.zeros_like(dem), ("synthetic",))
    frame = LocalFrame.centred_on(grid.bbox)
    scene = scene_input(grid, frame, [PARCEL])
    datum = float(scene["frame"]["datum_m"])
    floor = 100.0 - datum + 0.3
    offer = replace(offer, floor_range=(floor - 0.3, floor + 0.7))
    raw = {"placement": 1, "floor_z_m": floor, "roof": roof, "eaves_m": 0.6, "deck": deck}
    spec = parse_spec(json.dumps(raw))

    outputs = run_design(scene, spec_to_script(spec, offer), tmp_path)

    proposal = to_proposal(parse_measurements(outputs.measurements), frame, datum)
    report = evaluate(proposal, SiteContext(parcels=(PARCEL,), terrain=grid), product)
    assert report.status is not Status.FAIL, [c.detail for c in report.checks if c.status == "fail"]
    statuses = {c.name: c.status for c in report.checks}
    assert statuses["height"] is statuses["floor_level"] is statuses["floor_area"] is Status.PASS
    assert proposal.floor_level_m == pytest.approx(datum + floor, abs=1e-4)
    assert proposal.height_above_floor_m == pytest.approx(height_above_floor(spec, offer), abs=1e-4)
    assert Polygon(proposal.footprint).area == pytest.approx(
        offer.length_m * offer.width_m, abs=1e-3
    )
    # Blender's mesh has the outline the same triangles have measured here.
    built = dwelling(spec, offer)
    here = parse_measurements({"triangles": built.triangles(), "floor_area_m2": 1.0})
    assert here.outline is not None and proposal.outline is not None
    there = Polygon(frame.to_local(p) for p in proposal.outline)
    assert there.symmetric_difference(Polygon(here.outline)).area == pytest.approx(0.0, abs=1e-3)
    assert proposal.floor_area_m2 == pytest.approx(built.floor_area_m2)
    assert proposal.storeys == 1
    assert outputs.png is not None and outputs.png.is_file()
    return proposal
