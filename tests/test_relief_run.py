"""Running the relief tiers cheapest first, each published the moment it's ready."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from button_nz.relief import SiteRelief
from button_nz.relief.run import (
    DEPTH,
    MANIFEST,
    PARALLAX,
    ReliefFailed,
    Tier,
    TierOutput,
    run_relief,
)


def _relief() -> SiteRelief:
    surface = np.zeros((10, 12))
    surface[4:6, 5:8] = 3.0  # a shed
    aerial = np.full((40, 48, 3), 120, dtype=np.uint8)
    return SiteRelief(aerial, surface, 1.0, 0.25)


def _manifest(out: Path) -> dict[str, Any]:
    found: dict[str, Any] = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    return found


def _by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {tier["tier"]: tier for tier in manifest["tiers"]}


def test_each_tier_is_published_before_the_next_starts(tmp_path: Path) -> None:
    seen: list[dict[str, dict[str, Any]]] = []

    def quick(relief: SiteRelief, out: Path) -> TierOutput:
        seen.append(_by_name(_manifest(out)))
        (out / "quick.txt").write_text("q")
        return TierOutput({"view": "quick.txt"}, {"rows": 40.0})

    def slow(relief: SiteRelief, out: Path) -> TierOutput:
        seen.append(_by_name(_manifest(out)))
        return TierOutput({}, {})

    run_relief(_relief(), tmp_path, (Tier("quick", quick), Tier("slow", slow)))
    before_quick, before_slow = seen
    assert [t["status"] for t in before_quick.values()] == ["running", "pending"]
    assert before_slow["quick"]["status"] == "ready"
    assert before_slow["quick"]["files"] == {"view": "quick.txt"}
    assert before_slow["quick"]["facts"] == {"rows": 40.0}
    assert before_slow["quick"]["seconds"] >= 0
    assert before_slow["slow"]["status"] == "running"
    assert _by_name(_manifest(tmp_path))["slow"]["status"] == "ready"


def test_a_failed_tier_is_recorded_and_raised_after_the_rest(tmp_path: Path) -> None:
    ran: list[str] = []

    def broken(relief: SiteRelief, out: Path) -> TierOutput:
        raise RuntimeError("no GPU available to Cycles")

    def after(relief: SiteRelief, out: Path) -> TierOutput:
        ran.append("after")
        return TierOutput({}, {})

    with pytest.raises(ReliefFailed, match="broken: no GPU available to Cycles"):
        run_relief(_relief(), tmp_path, (Tier("broken", broken), Tier("after", after)))
    tiers = _by_name(_manifest(tmp_path))
    assert tiers["broken"]["status"] == "failed"
    assert tiers["broken"]["error"] == "no GPU available to Cycles"
    assert tiers["after"]["status"] == "ready" and ran == ["after"]


def test_the_quick_tiers_write_their_views(tmp_path: Path) -> None:
    run_relief(_relief(), tmp_path, (DEPTH, PARALLAX))
    tiers = _by_name(_manifest(tmp_path))
    assert tiers["depth"]["facts"] == {"low_m": 0.0, "high_m": 3.0}
    for tier in ("depth", "parallax"):
        for name in tiers[tier]["files"].values():
            assert (tmp_path / name).stat().st_size > 0
    assert set(tiers["parallax"]["files"]) == {"still", "video"}
