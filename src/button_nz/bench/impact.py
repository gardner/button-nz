"""What the town screen would mean for a town's housing (#127).

    uv run python -m button_nz.bench.impact docs/results/impact

If some share of the properties with room for a real prefab added one
dwelling each: how many homes, how much bigger the town's housing stock, and
how many people housed. The properties come from the town screen's own
results (``docs/results/town-screen``), counted by title (#122). The town's
existing housing comes from Stats NZ's 2023 Census, recorded with its source
in ``data/census/``. The shares are scenarios, not forecasts.
"""

import argparse
import json
import math
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TOWN_RESULTS = ROOT / "docs" / "results" / "town-screen" / "results.jsonl"
CENSUS_FILE = ROOT / "data" / "census" / "reefton-2023.json"
SHARES = (0.10, 0.25, 0.50)


@dataclass(frozen=True)
class Census:
    year: int
    population: int  # usually resident
    households: int
    dwellings: int  # private dwellings, occupied and not

    @property
    def people_per_household(self) -> float:
        return self.population / self.households

    @classmethod
    def read(cls, path: Path) -> tuple[Census, dict[str, Any]]:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        census = cls(
            year=int(raw["census_year"]),
            population=int(raw["usually_resident_population"]),
            households=int(raw["households"]),
            dwellings=int(raw["private_dwellings"]["total"]),
        )
        return census, raw


@dataclass(frozen=True)
class Scenario:
    share: float  # of the properties with room that add a dwelling
    homes: int
    increase: float  # of the town's private dwellings
    people_low: int  # one person a flat
    people_high: int  # the town's own people per household


def property_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Properties, and those with room (on LINZ's outlines, with eaves) and
    room also clear on the LiDAR: a property counts if any of its parcels does."""
    room: dict[int, bool] = {}
    clear: dict[int, bool] = {}
    for r in rows:
        pid = int(r["property_id"])
        room[pid] = room.get(pid, False) or bool(r["fits_eaves"])
        clear[pid] = clear.get(pid, False) or bool(r["clear_eaves"])
    return {"properties": len(room), "room": sum(room.values()), "clear": sum(clear.values())}


def scenarios(count: int, census: Census, shares: Sequence[float] = SHARES) -> list[Scenario]:
    """Each share of ``count`` properties adding one dwelling, in whole homes."""
    found: list[Scenario] = []
    for share in shares:
        homes = math.floor(count * share + 1e-9)
        found.append(
            Scenario(
                share=share,
                homes=homes,
                increase=homes / census.dwellings,
                people_low=homes,
                people_high=math.floor(homes * census.people_per_household + 1e-9),
            )
        )
    return found


def report(counts: Mapping[str, int], census: Census, raw: Mapping[str, Any], commit: str) -> str:
    rows = [
        "| Properties adding a flat | Homes | More homes than today | People housed |",
        "|---|---|---|---|",
    ]

    def table(count: int) -> list[str]:
        return rows + [
            f"| {s.share:.0%} of {count} | {s.homes} | +{s.increase:.0%} | "
            f"{s.people_low}–{s.people_high} |"
            for s in scenarios(count, census)
        ]

    return "\n".join(
        [
            "# Impact: what the town screen would mean for Reefton's housing",
            "",
            f"Code `{commit}`. Properties from the town screen "
            "([report](../town-screen/report.md)), counted by title. Today's housing from "
            f"{raw['source']} (retrieved {raw['retrieved']}, {raw['licence']}): "
            f"{census.dwellings} private dwellings, {census.households} households and "
            f"{census.population:,} people in {census.year}, "
            f"{census.people_per_household:.1f} people per household.",
            "",
            f"Of Reefton's {counts['properties']} residential properties, {counts['room']} have "
            "room for a real prefab on LINZ's building outlines (with 0.6 m eaves), and "
            f"{counts['clear']} also clear of everything over 2 m on the LiDAR.",
            "",
            "## On LINZ's outlines",
            "",
            *table(counts["room"]),
            "",
            "## Also clear on the LiDAR (stricter)",
            "",
            *table(counts["clear"]),
            "",
            "## How to read it",
            "",
            "- **The shares are scenarios, not forecasts.** Nothing here says how many "
            "owners would build.",
            "- **People housed** runs from one person a flat to the town's own "
            f"{census.people_per_household:.1f} people per household: a one-bedroom flat "
            "may house fewer than an average home.",
            "- **The areas differ.** The census's Reefton (a statistical area) and the town "
            "screen's Residential zones aren't the same boundary, so the increase is "
            "indicative.",
            f"- **Rounding.** {raw['note']}",
            "- **It's a screen, not consent:** hazards, slope, the district plan and "
            "services aren't checked (see the town screen's report).",
            "",
        ]
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The town screen's housing impact (#127).")
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args(argv)
    rows = [
        json.loads(line) for line in TOWN_RESULTS.read_text(encoding="utf-8").splitlines() if line
    ]
    census, raw = Census.read(CENSUS_FILE)
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    text = report(property_counts(rows), census, raw, commit)
    (args.out_dir / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
