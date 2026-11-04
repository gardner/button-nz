"""The relief views on the demo site (#149): how soon each tier is ready.

    uv run python -m button_nz.bench.relief docs/results/relief \\
        --full ~/src/button-nz-results/relief

Reads the demo site's DEM, DSM and aerial from LINZ, runs every tier into
``--full`` (clips, frames and all), then writes the report, each tier's
time (``results.json``) and its still to ``out_dir``. Times count from when
the site's data is in memory, as it is for a built site in the app; reading
it from LINZ is reported apart. The fly-over needs a GPU with room (``blender_worker.run``).
"""

import argparse
import json
import shutil
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from button_nz.agent.demo import demo_aerial, design_site
from button_nz.bench.provenance import code_commit
from button_nz.demo_site import load_demo_site
from button_nz.perception.survey import PIXEL_M
from button_nz.relief import SiteRelief
from button_nz.relief.run import MANIFEST, TIERS, ReliefFailed, run_relief

STILL = {"depth": "preview"}  # each tier's file to show; "still" for the rest
RESULTS = "results.json"


def report(entries: Sequence[Mapping[str, Any]], site_s: float, commit: str, where: str) -> str:
    lines = [
        "# Relief views: how soon each is ready (#149)",
        "",
        f"The demo site, {where}; code {commit}. Reading its DEM, DSM and aerial",
        f"from LINZ took {site_s:.1f} s, before any tier ran; a built site in the app",
        "has them on disk. **Ready after** counts from when the tiers start, so it",
        "is how long an owner waits for each view.",
        "",
        "| Tier | Status | Ready after (s) | Took (s) |",
        "|---|---|---|---|",
    ]
    elapsed = 0.0
    for entry in entries:
        elapsed += float(entry["seconds"])
        ready = entry["status"] == "ready"
        status = "ready" if ready else f"{entry['status']}: {entry.get('error', '')}"
        after = f"{elapsed:.2f}" if ready else "—"
        lines.append(f"| {entry['tier']} | {status} | {after} | {float(entry['seconds']):.2f} |")
    lines.append("")
    for entry in entries:
        if entry["status"] == "ready":
            name = entry["files"][STILL.get(entry["tier"], "still")]
            lines += [f"![{entry['tier']}]({name})", ""]
    return "\n".join(lines)


def published(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The run's tiers as the results keep them: without their files, which
    stay in the full run (only each still is copied, and named in the report)."""
    return [{key: value for key, value in e.items() if key != "files"} for e in entries]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The relief views on the demo site (#149).")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--full", type=Path, required=True, help="every output, clips included")
    args = parser.parse_args(argv)
    commit = code_commit()
    started = time.perf_counter()
    demo = load_demo_site()
    site = design_site(demo)
    grid = site.context.terrain
    datum = float(site.scene["frame"]["datum_m"])
    aerial = demo_aerial(site, PIXEL_M)
    relief = SiteRelief(aerial, grid.dem + grid.ndsm - datum, grid.cell_m, PIXEL_M)
    site_s = time.perf_counter() - started
    try:
        run_relief(relief, args.full, TIERS)
    except ReliefFailed as error:
        print(f"relief failed: {error}")  # reported in full below, then raised
        _write(args.out_dir, args.full, site_s, commit, demo.name)
        raise
    _write(args.out_dir, args.full, site_s, commit, demo.name)


def _write(out_dir: Path, full: Path, site_s: float, commit: str, where: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = json.loads((full / MANIFEST).read_text("utf-8"))["tiers"]
    for entry in entries:
        if entry["status"] == "ready":
            shutil.copy2(full / entry["files"][STILL.get(entry["tier"], "still")], out_dir)
    results = json.dumps({"code": commit, "tiers": published(entries)}, indent=1)
    (out_dir / RESULTS).write_text(results + "\n", encoding="utf-8")
    text = report(entries, site_s, commit, where)
    (out_dir / "report.md").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
