"""Design on many real sections and record what goes wrong (#117).

    uv run python -m button_nz.bench.batch --api http://127.0.0.1:8000 \\
        --sections 20 --out docs/results/batch/<label>

It drives the API as the app does: each section's site is built from its
LINZ address, a design is asked for, and its result is read back. Sections
are those the town screen says have room, spread across their range of sizes.
Each brief tests a placement the owner cares about. Per design it records:
- acceptance and the attempts taken;
- every check's verdict;
- whether the plan is a plain rectangle;
- how far the walls are from the address's street, and from each road the
  title faces (worked out here from LINZ, so a run on older code is measured
  the same way).

It's live and paid: each design is Meta Model API calls and a Blender run,
within the server's daily cap. A refusal (the cap's 429) stops the run, with
what was done so far kept: run it again to go on.
"""

import argparse
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from shapely import LineString, Polygon
from shapely.geometry import shape

from button_nz.geo.geometry import Point
from button_nz.sites.frontages import Frontage

BRIEFS = (
    "A compact studio as far from the street as the rules allow",
    "A two-bedroom flat for Mum, keeping the trees",
    "A one-bedroom studio that gets the afternoon sun",
)
RIGHT_ANGLE_TOLERANCE_DEG = 2.0


def pick(sections: Sequence[dict[str, Any]], count: int) -> list[int]:
    """``count`` sections with room ("clear" on the town screen), spread evenly
    across their range of sizes: the same picks each run."""
    room = sorted(
        (shape(s["geometry"]).area, int(s["properties"]["id"]))
        for s in sections
        if s["properties"]["category"] == "clear"
    )
    if count >= len(room):
        return [pid for _, pid in room]
    if count == 1:
        return [room[0][1]]
    last = len(room) - 1
    return [room[round(i * last / (count - 1))][1] for i in range(count)]


def is_rectangle(walls: Sequence[Point]) -> bool:
    """Whether the walls are four corners, each square to within a couple of degrees."""
    simple = cast("Polygon", Polygon(walls).simplify(0.05))
    corners = [(float(x), float(y)) for x, y in simple.exterior.coords][:-1]
    if len(corners) != 4:
        return False
    return all(_square(corners[i - 1], corners[i], corners[(i + 1) % 4]) for i in range(4))


def _square(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> bool:
    """Whether the corner at ``b`` is a right angle, either way round."""
    turn = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0]))
    return min(abs(turn % 180 - 90), abs(turn % 180 + 90)) <= RIGHT_ANGLE_TOLERANCE_DEG


def street_distance(walls: Sequence[Point], found: Sequence[Frontage]) -> float | None:
    """How far the walls are from the address's street's edge; None if the
    site has no street among its frontages."""
    street = next((f for f in found if f.street), None)
    if street is None:
        return None
    footprint = Polygon(walls)
    return round(min(footprint.distance(LineString(edge)) for edge in street.edges), 2)


def road_distances(walls: Sequence[Point], found: Sequence[Frontage]) -> dict[str, float]:
    """How far the walls are from each frontage, by its road's name."""
    footprint = Polygon(walls)
    return {
        f.road or "unnamed road": round(min(footprint.distance(LineString(e)) for e in f.edges), 2)
        for f in found
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Design on many real sections.")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--sections", type=int, default=20)
    parser.add_argument("--town", default="reefton")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    from button_nz.bench.batch_run import run_batch  # live: LINZ and the API

    run_batch(args.api, args.town, args.sections, args.out)


if __name__ == "__main__":
    main()
