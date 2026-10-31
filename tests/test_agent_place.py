"""Tests for designing to a real product's footprint (button_nz.agent.loop)."""

from pathlib import Path

import pytest

from button_nz.agent.loop import DesignResult, DesignSite, design
from button_nz.evaluation import Footprint, Status
from test_agent_loop import ScriptedModel, fake_runner, flat_site

SIX_BY_FIVE = Footprint("Test Cabin", length_m=6.0, width_m=5.0)  # GOOD's walls
EIGHT_BY_FOUR = Footprint("Long Cabin", length_m=8.0, width_m=4.0)


@pytest.fixture
def site() -> DesignSite:
    return flat_site()


def place(
    site: DesignSite, model: ScriptedModel, tmp_path: Path, product: Footprint
) -> DesignResult:
    return design(
        "A studio for the garden.", site, model, tmp_path, runner=fake_runner, product=product
    )


def test_the_brief_says_which_product_to_place_and_its_footprint(
    site: DesignSite, tmp_path: Path
) -> None:
    model = ScriptedModel("good")
    place(site, model, tmp_path, SIX_BY_FIVE)
    brief = model.seen[0][1].text
    assert brief.startswith("A studio for the garden.")
    assert "Test Cabin" in brief
    assert "6 × 5 m" in brief


def test_walls_that_are_the_product_are_accepted(site: DesignSite, tmp_path: Path) -> None:
    result = place(site, ScriptedModel("good"), tmp_path, SIX_BY_FIVE)
    assert result.accepted is result.attempts[0]
    report = result.attempts[0].report
    assert report is not None
    assert report.checks[0].name == "product_footprint"
    assert report.checks[0].status is Status.PASS


def test_walls_that_are_not_the_product_fail_and_are_fed_back(
    site: DesignSite, tmp_path: Path
) -> None:
    model = ScriptedModel("good", "good", "good")
    result = place(site, model, tmp_path, EIGHT_BY_FOUR)
    assert result.accepted is None
    assert "product_footprint: fail" in model.seen[1][-1].text
    assert "the Long Cabin is 8 × 4 m" in model.seen[1][-1].text
