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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from button_nz.bench.provenance import code_commit

ROOT = Path(__file__).resolve().parents[3]
TOWN_RESULTS = ROOT / "docs" / "results" / "town-screen" / "results.jsonl"
CENSUS_FILE = ROOT / "data" / "census" / "reefton-2023.json"
SHARES = (0.10, 0.25, 0.50)


@dataclass(frozen=True)
class Census:
    year: int
    population: int  # usually resident, private and non-private dwellings
    households: int
    dwellings: int  # private dwellings, occupied and not
    household_size: float  # mean usual residents per household (private dwellings)

    @classmethod
    def read(cls, path: Path) -> tuple[Census, dict[str, Any]]:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        census = cls(
            year=int(raw["census_year"]),
            population=int(raw["usually_resident_population"]),
            households=int(raw["households"]),
            dwellings=int(raw["private_dwellings"]["total"]),
            household_size=_mean_size(raw["household_size"]["counts"]),
        )
        return census, raw


def _mean_size(counts: Mapping[str, int]) -> float:
    """The mean household size from Stats NZ's households-by-size counts.
    "8+" counts as 8, so a town with any such households would be understated:
    it's refused rather than guessed."""
    if counts.get("8+", 0):
        raise ValueError("households of eight or more: their size isn't known")
    sized = {int(k): v for k, v in counts.items() if k != "8+"}
    return sum(k * v for k, v in sized.items()) / sum(sized.values())  # rounded when shown


@dataclass(frozen=True)
class Scenario:
    share: float  # of the properties with room that add a dwelling
    homes: int
    increase: float  # of the town's private dwellings
    people_low: int  # one person a flat
    people_high: int  # the town's own mean household size


def property_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Properties counted once each (a title of one or more parcels):
    - backyards: properties with a LINZ building outline, taken to hold a home
      a flat would be a second one beside (the outlines don't say which
      building is a home, so the report says so); with room on LINZ's
      outlines (eaves allowed), and room also clear on the LiDAR;
    - empty sections with room, where a dwelling would be a first home, which
      was allowed before the exemption: reported apart, never as flats."""
    built: dict[int, bool] = {}
    room: dict[int, bool] = {}
    clear: dict[int, bool] = {}
    for r in rows:
        pid = int(r["property_id"])
        built[pid] = built.get(pid, False) or bool(r["buildings"])
        room[pid] = room.get(pid, False) or bool(r["fits_eaves"])
        clear[pid] = clear.get(pid, False) or bool(r["clear_eaves"])
    return {
        "properties": len(built),
        "backyards": sum(built.values()),
        "backyard_room": sum(1 for p in built if built[p] and room[p]),
        "backyard_clear": sum(1 for p in built if built[p] and clear[p]),
        "empty_room": sum(1 for p in built if not built[p] and room[p]),
    }


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
                people_high=math.floor(homes * census.household_size + 1e-9),
            )
        )
    return found


def report(counts: Mapping[str, int], census: Census, raw: Mapping[str, Any], commit: str) -> str:
    header = [
        "| Backyards adding a flat | Homes | More homes than today | People housed |",
        "|---|---|---|---|",
    ]

    def table(count: int) -> list[str]:
        return header + [
            f"| {s.share:.0%} of {count} | {s.homes} | +{s.increase:.0%} | "
            f"{s.people_low}–{s.people_high} |"
            for s in scenarios(count, census)
        ]

    sized = sum(raw["household_size"]["counts"].values())  # households with a stated size
    single = raw["household_size"]["counts"]["1"] / sized
    return "\n".join(
        [
            "# Impact: what the town screen would mean for Reefton's housing",
            "",
            f"Code `{commit}`. Properties from the town screen "
            "([report](../town-screen/report.md)), counted by title. Today's housing from "
            f"{raw['source']} (retrieved {raw['retrieved']}, {raw['licence']}): "
            f"{census.dwellings} private dwellings, {census.households:,} households and "
            f"{census.population:,} people in {census.year}; households average "
            f"{census.household_size:.2f} people, and {single:.0%} are one person (of the "
            f"{sized} households whose size Stats NZ gives).",
            "",
            f"Of Reefton's {counts['properties']} residential properties, {counts['backyards']} "
            "have a LINZ building outline on them. Of those **backyards**, "
            f"{counts['backyard_room']} have room for a real prefab on LINZ's building "
            "outlines (with 0.6 m eaves), and "
            f"{counts['backyard_clear']} also clear of everything over 2 m on the LiDAR. A flat "
            "there is a second home beside the first: what the exemption adds.",
            "",
            "## Backyards, on LINZ's outlines",
            "",
            *table(counts["backyard_room"]),
            "",
            "## Backyards, also clear on the LiDAR (stricter)",
            "",
            *table(counts["backyard_clear"]),
            "",
            "## Empty sections",
            "",
            f"Another {counts['empty_room']} properties with room have no building. A dwelling "
            "there would be a first home, which was allowed before the exemption, so they "
            "aren't counted as flats above.",
            "",
            "## How to read it",
            "",
            "- **The shares are scenarios, not forecasts.** Nothing here says how many "
            "owners would build.",
            "- **People housed** runs from one person a flat to Reefton's average household "
            f"of {census.household_size:.2f} (from Stats NZ's households by size).",
            "- **A backyard is a property with a LINZ building outline**, taken to hold a "
            "home. The outlines don't say which building is a home: a property whose only "
            "outline is a garage or shed counts as a backyard, and a house built since the "
            "2015–16 aerial photos is missing, so its property counts as an empty section.",
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
    commit = code_commit(str(TOWN_RESULTS.relative_to(ROOT)))  # the screen's results too
    args.out_dir.mkdir(parents=True, exist_ok=True)
    text = report(property_counts(rows), census, raw, commit)
    (args.out_dir / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
