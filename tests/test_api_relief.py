"""A ready site's relief views over HTTP (button_nz.api.relief): made when
asked for, one site at a time, and served from the site's own directory."""

import json
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from button_nz.relief import SiteRelief
from button_nz.relief.flyover import WORK_DIRS
from button_nz.relief.run import MANIFEST, Tier, TierOutput
from test_api_sites import Server

WAIT_S = 10.0


def _clip(relief: SiteRelief, out: Path) -> TierOutput:
    (out / "clip.mp4").write_bytes(b"mp4 of " + bytes(str(relief.aerial.shape), "ascii"))
    return TierOutput({"video": "clip.mp4"}, {"frames": 2.0})


CLIP = Tier("parallax", _clip)


def _made(server: Server, site_id: str) -> dict[str, Any]:
    """The site's relief once nothing is making it."""
    deadline = time.monotonic() + WAIT_S
    while True:
        shown: dict[str, Any] = server.client.get(f"/sites/{site_id}/relief").json()
        if not shown["making"]:
            return shown
        assert time.monotonic() < deadline, shown
        time.sleep(0.02)


def test_a_ready_sites_relief_is_made_when_asked_and_its_files_served(tmp_path: Path) -> None:
    server = Server(tmp_path, relief_tiers=(CLIP,))
    site_id = server.build()["id"]
    before = server.client.get(f"/sites/{site_id}/relief")
    assert before.json() == {"making": False, "tiers": []}
    assert before.headers["cache-control"] == "no-store"
    asked = server.client.post(f"/sites/{site_id}/relief")
    assert asked.status_code == 202 and asked.json()["making"] is True
    (tier,) = _made(server, site_id)["tiers"]
    assert tier["tier"] == "parallax" and tier["status"] == "ready"
    url = f"/sites/{site_id}/relief/clip.mp4"
    assert tier["files"] == {"video": url}
    clip = server.client.get(url)
    assert clip.headers["content-type"] == "video/mp4"
    assert clip.headers["cache-control"] == "no-cache"
    # The built site's aerial over its LiDAR grid, at the survey's 12.5 cm.
    rows, cols = _grid_pixels(tmp_path, site_id)
    assert clip.content == f"mp4 of ({rows}, {cols}, 3)".encode()
    assert (tmp_path / "sites" / site_id / "relief" / MANIFEST).is_file()


def _grid_pixels(tmp_path: Path, site_id: str) -> tuple[int, int]:
    west, south, east, north = json.loads((tmp_path / "sites" / site_id / "site.json").read_text())[
        "aerial_bbox"
    ]
    return round((north - south) / 0.125), round((east - west) / 0.125)


def test_the_relief_is_drawn_on_the_sites_own_heights(tmp_path: Path) -> None:
    seen: list[SiteRelief] = []

    def keep(relief: SiteRelief, out: Path) -> TierOutput:
        seen.append(relief)
        return TierOutput({}, {})

    server = Server(tmp_path, relief_tiers=(Tier("depth", keep),))
    site_id = server.build()["id"]
    server.client.post(f"/sites/{site_id}/relief")
    _made(server, site_id)
    (relief,) = seen
    design, _ = server.sites.design_site(site_id)
    grid = design.context.terrain
    datum = float(design.scene["frame"]["datum_m"])
    assert relief.cell_m == grid.cell_m and relief.pixel_m == 0.125
    np.testing.assert_allclose(relief.surface, grid.dem + grid.ndsm - datum)


def test_only_what_the_app_shows_is_kept(tmp_path: Path) -> None:
    def rendered(relief: SiteRelief, out: Path) -> TierOutput:
        for work in WORK_DIRS:  # the fly-over's inputs and frames, 100 MB a site
            (out / work).mkdir()
            (out / work / "frame_0000.png").write_bytes(b"png")
        return _clip(relief, out)

    server = Server(tmp_path, relief_tiers=(Tier("flyover", rendered),))
    site_id = server.build()["id"]
    server.client.post(f"/sites/{site_id}/relief")
    _made(server, site_id)
    kept = sorted(p.name for p in (tmp_path / "sites" / site_id / "relief").iterdir())
    assert kept == ["clip.mp4", MANIFEST]


def test_a_made_relief_is_not_made_again(tmp_path: Path) -> None:
    runs: list[str] = []

    def counted(relief: SiteRelief, out: Path) -> TierOutput:
        runs.append("run")
        return _clip(relief, out)

    server = Server(tmp_path, relief_tiers=(Tier("parallax", counted),))
    site_id = server.build()["id"]
    server.client.post(f"/sites/{site_id}/relief")
    _made(server, site_id)
    again = server.client.post(f"/sites/{site_id}/relief")
    assert again.status_code == 202 and again.json()["making"] is False
    assert again.json()["tiers"][0]["status"] == "ready"
    assert runs == ["run"]


def test_a_failed_tier_says_why_and_asking_again_makes_it_again(tmp_path: Path) -> None:
    tries: list[str] = []

    def busy_once(relief: SiteRelief, out: Path) -> TierOutput:
        tries.append("try")
        if len(tries) == 1:
            raise RuntimeError("no GPU has 4 GiB free")
        return TierOutput({}, {})

    server = Server(tmp_path, relief_tiers=(CLIP, Tier("flyover", busy_once)))
    site_id = server.build()["id"]
    server.client.post(f"/sites/{site_id}/relief")
    clip, flyover = _made(server, site_id)["tiers"]
    assert clip["status"] == "ready"
    assert flyover == {
        "tier": "flyover",
        "status": "failed",
        "error": "no GPU has 4 GiB free",
        "seconds": flyover["seconds"],
    }
    assert server.client.post(f"/sites/{site_id}/relief").json()["making"] is True
    assert [t["status"] for t in _made(server, site_id)["tiers"]] == ["ready", "ready"]


def test_a_tier_cut_off_by_a_restart_reads_as_failed(tmp_path: Path) -> None:
    server = Server(tmp_path, relief_tiers=(CLIP,))
    site_id = server.build()["id"]
    directory = tmp_path / "sites" / site_id / "relief"
    directory.mkdir()
    left = {"tiers": [{"tier": "parallax", "status": "running"}]}  # as a restart leaves it
    (directory / MANIFEST).write_text(json.dumps(left))
    (tier,) = server.client.get(f"/sites/{site_id}/relief").json()["tiers"]
    assert tier == {"tier": "parallax", "status": "failed", "error": "interrupted by a restart"}
    server.client.post(f"/sites/{site_id}/relief")
    assert _made(server, site_id)["tiers"][0]["status"] == "ready"


def test_a_relief_still_queued_at_a_restart_reads_as_failed(tmp_path: Path) -> None:
    rendering, done = threading.Event(), threading.Event()

    def busy(relief: SiteRelief, out: Path) -> TierOutput:
        rendering.set()
        done.wait(WAIT_S)  # another site's fly-over, still rendering
        return TierOutput({}, {})

    server = Server(tmp_path, relief_tiers=(Tier("flyover", busy),))
    first, second = server.build(7)["id"], server.build(8)["id"]
    server.client.post(f"/sites/{first}/relief")
    assert rendering.wait(WAIT_S)
    server.client.post(f"/sites/{second}/relief")  # queued behind the first
    try:
        restarted = Server(tmp_path, relief_tiers=(CLIP,))
        shown = restarted.client.get(f"/sites/{second}/relief").json()
        assert shown == {
            "making": False,
            "tiers": [{"tier": "flyover", "status": "failed", "error": "interrupted by a restart"}],
        }
    finally:
        done.set()


def test_a_site_whose_relief_cant_be_read_says_why(tmp_path: Path) -> None:
    server = Server(tmp_path, relief_tiers=(CLIP,))
    site_id = server.build()["id"]
    (tmp_path / "sites" / site_id / "aerial.png").unlink()
    server.client.post(f"/sites/{site_id}/relief")
    (tier,) = _made(server, site_id)["tiers"]
    assert tier["status"] == "failed" and "aerial.png" in tier["error"]


def test_one_sites_relief_is_made_at_a_time(tmp_path: Path) -> None:
    running, overlapped = threading.Lock(), list[Path]()

    def alone(relief: SiteRelief, out: Path) -> TierOutput:
        if not running.acquire(blocking=False):
            overlapped.append(out)
            return TierOutput({}, {})
        time.sleep(0.2)
        running.release()
        return TierOutput({}, {})

    server = Server(tmp_path, relief_tiers=(Tier("flyover", alone),))
    first, second = server.build(7)["id"], server.build(8)["id"]
    server.client.post(f"/sites/{first}/relief")
    server.client.post(f"/sites/{second}/relief")
    assert _made(server, first)["tiers"][0]["status"] == "ready"
    assert _made(server, second)["tiers"][0]["status"] == "ready"
    assert overlapped == []


def test_only_ready_sites_and_files_the_manifest_names_are_served(tmp_path: Path) -> None:
    server = Server(tmp_path, relief_tiers=(CLIP,))
    assert server.client.post("/sites/nowhere/relief").status_code == 404
    assert server.client.get("/sites/nowhere/relief").status_code == 404
    building = server.client.post("/sites", json={"address_id": 7}).json()["id"]
    assert server.client.post(f"/sites/{building}/relief").status_code == 409
    server.builder.run_next()
    assert server.client.get(f"/sites/{building}/relief/clip.mp4").status_code == 404
    server.client.post(f"/sites/{building}/relief")
    _made(server, building)
    for name in (MANIFEST, "..%2Fsite.json", "nothing.mp4"):
        assert server.client.get(f"/sites/{building}/relief/{name}").status_code == 404
