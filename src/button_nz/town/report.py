"""The town screen's results log, its counts and its report.

``results.jsonl`` holds one line per section, keyed by BDC's ParcelID alone:
no address, appellation, title or valuation, so the published results name
no one's property. The report is written from those results alone.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from button_nz.town.screen import EAVE_ALLOWANCE_M, SectionResult

COUNTS = ("fits", "fits_eaves", "clear", "clear_eaves")
LABELS = {
    "fits": "Room under LINZ outlines, stated dimensions",
    "fits_eaves": f"Room under LINZ outlines, with {EAVE_ALLOWANCE_M:g} m eaves",
    "clear": "Room clear of everything over 2 m on the LiDAR, stated dimensions",
    "clear_eaves": (
        f"Room clear of everything over 2 m on the LiDAR, with {EAVE_ALLOWANCE_M:g} m eaves"
    ),
}
SIZE_BANDS = ((0, 300), (300, 600), (600, 1000), (1000, None))  # m²

NOT_CHECKED = """\
- **Hazards**: flooding (Reefton sits beside the Inangahua River), rockfall,
  and whatever a PIM would note. A site the PIM marks as likely hazard-affected
  may not suit the exemption.
- **Slope and floor level**: the exemption limits the floor to 1 m above the
  ground; the screen doesn't look at the ground's shape.
- **The district plan and the NES-DMRU**: zone rules, site coverage, the
  number of habitable buildings per site, and whether a resource consent is
  needed.
- **Services**: water, wastewater, stormwater and power.
- **What neither dataset shows**: structures too small for LINZ's outlines and
  under 2 m tall, and anything built or removed since the LiDAR (2020–24).
- **Lines between parcels on one title**: each parcel is screened alone, as if
  every parcel boundary were a legal boundary. A title of several parcels may
  have more room than this shows.
- **Height, design and the exemption's other conditions**: these depend on
  the building, not the section.
"""


def write_results(results: Sequence[SectionResult], path: Path) -> Path:
    """One JSON line per section, in the order given."""
    lines = [json.dumps(_record(r), ensure_ascii=False) for r in results]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def summarise(results: Sequence[SectionResult]) -> dict[str, Any]:
    """How many sections have room for at least one product, in each count."""
    counts: dict[str, Any] = {
        "sections": len(results),
        "with_buildings": sum(1 for r in results if r.buildings),
    }
    for name in COUNTS:
        counts[name] = sum(1 for r in results if getattr(r, name))
    products = sorted({p for r in results for p in r.fits})
    counts["by_product"] = {
        p: {name: sum(1 for r in results if p in getattr(r, name)) for name in COUNTS}
        for p in products
    }
    return counts


def report(results: Sequence[SectionResult], meta: Mapping[str, Any]) -> str:
    """The Markdown report for ``results``; ``meta`` says how they were made."""
    counts = summarise(results)
    total = counts["sections"]
    lines = [
        f"# Town screen: room for a real prefab in {meta['place']}",
        "",
        _introduction(meta, total, counts["with_buildings"]),
        "",
        "| Count | Sections | Share |",
        "|---|---|---|",
        *(f"| {LABELS[n]} | {counts[n]} | {_share(counts[n], total)} |" for n in COUNTS),
        "",
        "## By section size",
        "",
        _by_size(results),
        "",
        "## By product",
        "",
        _by_product(counts["by_product"], meta["products"]),
        "",
        "## What it checks",
        "",
        _checks(),
        "",
        "## What it doesn't check",
        "",
        NOT_CHECKED,
        "## Sources",
        "",
        *(_source(s) for s in meta["sources"]),
        "",
    ]
    return "\n".join(lines)


def _introduction(meta: Mapping[str, Any], total: int, with_buildings: int) -> str:
    left = ", ".join(f"{intent}: {n}" for intent, n in sorted(meta["other_intent"].items()))
    return (
        f"Code `{meta['commit']}`. Envelope (NZTM2000) `{tuple(meta['envelope'])}`. "
        f"{total} residential sections: BDC parcels with a title whose point lies in a "
        f"Residential zone ({with_buildings} with more than 1 m² of a LINZ building outline "
        "on them). "
        f"Left out: {meta['outside_zone']} titles outside a Residential zone, and parcels "
        f"in one that aren't titles ({left or 'none'}). A section counts if at least one "
        "real prefab with labelled dimensions fits on it, square to one of its walls."
    )


def _by_size(results: Sequence[SectionResult]) -> str:
    rows = [
        "| Section area | Sections | With a building | "
        + " | ".join(LABELS[n] for n in ("fits_eaves", "clear_eaves"))
        + " |",
        "|---|---|---|---|---|",
    ]
    for low, high in SIZE_BANDS:
        band = [r for r in results if r.area_m2 >= low and (high is None or r.area_m2 < high)]
        name = f"{low}–{high} m²" if high else f"{low} m² and over"
        built = sum(1 for r in band if r.buildings)
        cells = [str(sum(1 for r in band if getattr(r, n))) for n in ("fits_eaves", "clear_eaves")]
        rows.append(f"| {name} | {len(band)} | {built} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _by_product(by_product: Mapping[str, Mapping[str, int]], names: Mapping[str, str]) -> str:
    rows = [
        "| Product | " + " | ".join(LABELS[n] for n in COUNTS) + " |",
        "|---|" + "---|" * len(COUNTS),
    ]
    for product, counts in sorted(by_product.items(), key=lambda kv: -kv[1]["fits"]):
        cells = " | ".join(str(counts[n]) for n in COUNTS)
        rows.append(f"| {names[product]} | {cells} |")
    return "\n".join(rows)


def _checks() -> str:
    return (
        "Schedule 1A's siting rules that need no site visit: the outline stands at least "
        "2 m inside the section's boundary and at least 2 m from every LINZ building "
        "outline, each treated as a residential building, and stays on one parcel. "
        "The LiDAR count also keeps 2 m from every 1 m cell the nDSM shows over 2 m "
        "above the ground: buildings newer than the outlines, but also trees and hedges, "
        "so it counts room without removing anything. Products are tried square to each "
        "of the room's walls and to its minimum rotated rectangle (`catalogue.fit`): a "
        "fit can be missed, never invented. Most suppliers don't publish eaves, so each "
        f"count is repeated with the outline grown by {EAVE_ALLOWANCE_M:g} m on every side."
    )


def _source(source: Mapping[str, str]) -> str:
    return (
        f"- **{source['title']}** ({source['licence']}; {source['attribution']}). "
        f"{source['dates']}. {source['service']}"
    )


def _record(result: SectionResult) -> dict[str, Any]:
    record = asdict(result)
    for key in ("area_m2", "room_m2", "clear_room_m2"):
        record[key] = round(record[key], 1)
    return record


def _share(count: int, total: int) -> str:
    return f"{100 * count / total:.0f}%" if total else "–"
