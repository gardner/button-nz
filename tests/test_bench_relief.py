"""The relief benchmark's report: when each tier's view is ready."""

from button_nz.bench.relief import published, report


def _entries() -> list[dict[str, object]]:
    return [
        {"tier": "depth", "status": "ready", "seconds": 0.07, "files": {"preview": "depth.png"}},
        {"tier": "parallax", "status": "ready", "seconds": 2.6, "files": {"still": "p.png"}},
        {"tier": "flyover", "status": "failed", "seconds": 1.0, "error": "no GPU"},
    ]


def test_each_tier_is_ready_after_those_before_it() -> None:
    text = report(_entries(), site_s=5.2, commit="abc1234", where="35 Victory Street, Reefton")
    assert "abc1234" in text and "35 Victory Street, Reefton" in text
    assert "| depth | ready | 0.07 | 0.07 |" in text
    assert "| parallax | ready | 2.67 | 2.60 |" in text
    assert "| flyover | failed: no GPU | — | 1.00 |" in text


def test_shows_each_ready_tiers_still() -> None:
    text = report(_entries(), site_s=5.2, commit="abc1234", where="x")
    assert "![depth](depth.png)" in text and "![parallax](p.png)" in text


def test_publishes_the_run_without_the_files_it_doesnt_keep() -> None:
    kept = published(_entries())
    assert [entry["tier"] for entry in kept] == ["depth", "parallax", "flyover"]
    assert all("files" not in entry for entry in kept)
    assert kept[2]["error"] == "no GPU" and kept[0]["seconds"] == 0.07
