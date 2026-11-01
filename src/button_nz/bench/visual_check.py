"""How often the AI visual passes its silhouette check (#133), on recorded designs.

    uv run python -m button_nz.bench.visual_check RUNS_DIR DESIGN_ID...

Re-makes each design's visual as the app does (``perception.visual.illustrate``,
on its accepted attempt-1 render and silhouette) and prints one line per
design: its id, PASS or fail, the edits made and the best IoU. Live: it calls
the Meta Model API with ``META_API_KEY``, about 25 s and one billed edit each.
"""

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from button_nz.perception.sam import Segmenter
from button_nz.perception.visual import illustrate, visual_client


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The AI visual's pass rate (#133).")
    parser.add_argument("runs", type=Path, help="the API's runs directory")
    parser.add_argument("designs", nargs="+")
    args = parser.parse_args(argv)
    client = visual_client(os.environ["META_API_KEY"])
    segmenter = Segmenter(client)
    passed = 0
    for design in args.designs:
        attempt = args.runs / design / "attempt-1"
        visual = illustrate(
            attempt / "design.png", attempt / "dwelling-mask.png", client, segmenter
        )
        passed += visual.accepted
        iou = "none" if visual.iou is None else f"{visual.iou:.2f}"
        verdict = "PASS" if visual.accepted else "fail"
        print(f"{design} {verdict} edits={visual.edits} iou={iou}", flush=True)
    print(f"{passed} of {len(args.designs)} passed")


if __name__ == "__main__":
    main()
