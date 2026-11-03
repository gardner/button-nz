"""How often the AI visual passes its silhouette check (#133), on recorded designs.

    uv run python -m button_nz.bench.visual_check RUNS_DIR DESIGN_ID... [--save DIR]

Re-makes each design's visual as the app does (``perception.visual.illustrate``,
on its accepted attempt's render, silhouette and whole outline) and prints one
line per design: its id, PASS or fail, the edits made and the best IoUs with the
silhouette and with the whole outline. With ``--save``,
each design's ``visual.json``, and its picture if accepted, are kept under
``DIR/<design id>`` for review. Live: it calls
the Meta Model API with ``META_API_KEY``: one billed edit and SAM call per
design, or two when the first is rejected, about 25 s each.
"""

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from button_nz.perception.sam import Segmenter
from button_nz.perception.visual import Visual, illustrate, save, visual_client


def accepted_attempt(runs: Path, design: str) -> Path:
    """The directory of the design's accepted attempt: the one the app illustrates."""
    summary = json.loads((runs / design / "design.json").read_text(encoding="utf-8"))
    number = summary["accepted_attempt"]
    if number is None:
        raise ValueError(f"design {design} has no accepted attempt: it has no visual")
    return runs / design / f"attempt-{int(number)}"


def keep(visual: Visual, directory: Path, design: str) -> None:
    """Save ``visual`` as the app would, under ``directory/design``."""
    (directory / design).mkdir(parents=True, exist_ok=True)
    save(visual, directory / design)


def _number(value: float | None) -> str:
    return "none" if value is None else f"{value:.2f}"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The AI visual's pass rate (#133).")
    parser.add_argument("runs", type=Path, help="the API's runs directory")
    parser.add_argument("designs", nargs="+")
    parser.add_argument("--save", type=Path, help="keep each visual under this directory")
    args = parser.parse_args(argv)
    client = visual_client(os.environ["META_API_KEY"])
    segmenter = Segmenter(client)
    passed = 0
    for design in args.designs:
        attempt = accepted_attempt(args.runs, design)
        silhouettes = (attempt / "dwelling-mask.png", attempt / "dwelling-outline.png")
        visual = illustrate(attempt / "design.png", *silhouettes, client, segmenter)
        passed += visual.accepted
        if args.save is not None:
            keep(visual, args.save, design)
        verdict = "PASS" if visual.accepted else "fail"
        ious = f"iou={_number(visual.iou)} outline_iou={_number(visual.outline_iou)}"
        print(f"{design} {verdict} edits={visual.edits} {ious}", flush=True)
    print(f"{passed} of {len(args.designs)} passed")


if __name__ == "__main__":
    main()
