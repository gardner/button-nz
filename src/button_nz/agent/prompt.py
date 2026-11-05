"""What the design model is told: the design spec, the rules it is checked
against, the site in its local frame with the placements it is offered, and
each attempt's verdicts."""

from collections.abc import Sequence

from button_nz.agent.build import FASCIA_M, FLOOR_M, steepest_pitch
from button_nz.agent.offers import Offer, Offers, heading
from button_nz.agent.placement import PROMPT_EAVES_M
from button_nz.blender_worker.scene_input import SceneInput
from button_nz.evaluation import Footprint, Report
from button_nz.evaluation.checks import (
    MAX_FLOOR_ABOVE_GROUND_M,
    MAX_FLOOR_AREA_M2,
    MAX_HEIGHT_ABOVE_FLOOR_M,
    MIN_SEPARATION_M,
)
from button_nz.geo.geometry import Ring

STOREY_WALLS_M = 2.4  # the walls the steepest pitches are given for

CONTRACT = """You design a small detached dwelling on a real New Zealand property. You \
don't model it: call the propose_design tool with a design spec, choosing one of the \
placements offered below and the parameters that best serve the brief. Tested code \
builds the spec in Blender as one closed envelope: the walls on their floor, the roof \
over them and its eaves, and a deck if it has one.

The spec, in a local frame in metres (x east, y north, z up, z relative to the datum \
below):
- placement: an offered placement's number. It fixes the walls: their plan, where \
they stand and which way they face.
- floor_z_m: the floor's underside, within that placement's floor range.
- wall_height_m: from the floor's underside, a {floor_m:g} m floor and then walls this \
high (2.1 to 3.0; 2.4 if omitted).
- roof: its form, gable or hip (the ridge along the long walls), skillion (one slope, \
rising to the wall named by high_side) or flat, at pitch_deg. Over the walls is a \
{fascia_m:g} m roof edge, then the roof's rise: (half the plan's width + the eaves) \
x tan(pitch) for a gable or hip, the roof's whole depth across x tan(pitch) for a \
skillion, none for a flat roof.
- eaves_m: how far the roof overhangs the walls all round, 0 to {eaves:g}.
- deck (optional): beside the wall facing side, depth_m out from it (1 to 3), width_m \
along it (the whole wall if omitted); a thin slab level with the floor.
- openings (optional): windows and doors on each side, for the illustration; the \
massing model doesn't cut them.
Sides are the compass points the placement's walls face, as each placement lists them.

An independent evaluator measures the Dwelling that is built and checks it. You \
cannot argue with a check; change the spec instead. Checks, from Schedule 1A of the \
Building Act 2004 (the granny flats exemption):
- inside the title's parcels;
- at least {sep:g} m from the title boundary, from internal section lines \
(reported as unknown if closer: their legal status is unconfirmed) and from \
confirmed residential buildings, measured from everything the building covers, \
eaves and deck included;
- internal floor area at most {area:g} m²; single storey; at most {height:g} m \
above the floor (its underside);
- floor at most {floor:g} m above the lowest ground under the walls, and not \
below the highest;
- clear of the owner's preservation areas.
"Unknown" means it could not be verified; it is reported, never treated as a pass.
Every offered placement passes the siting checks with its walls and {eaves:g} m eaves; \
a deck adds to what is checked, so give it a side with room to spare.

If observation tools are offered (hillshade, contours, height maps, cross-sections, \
elevation statistics), you may call them before a design to look at the measured \
site, in the same local coordinates, with heights in scene z. They re-present the \
LiDAR; use them when you are unsure about slopes, banks or what stands on the ground.
"""

# How it should look, within the rules.
HOME = (
    "\nTo look like a real New Zealand home, within those rules: where the brief and the "
    "site suit one, add a deck on the sunny (north) or living side. A compact studio or "
    "a tight site can do without.\n"
)


def system_prompt(
    scene: SceneInput,
    keep_clear: Sequence[Ring] = (),
    buildings: Sequence[Ring] = (),
    frontages: str = "",
) -> str:
    """The contract and the site. ``keep_clear`` (the owner's preservation areas)
    and ``buildings`` (existing ones the owner listed) are local rings;
    ``frontages`` describes the site in words: which edges face which road
    (``sites.frontages.describe_frontages``), the room, the offered placements."""
    rules = CONTRACT.format(
        sep=MIN_SEPARATION_M,
        area=MAX_FLOOR_AREA_M2,
        height=MAX_HEIGHT_ABOVE_FLOOR_M,
        floor=MAX_FLOOR_ABOVE_GROUND_M,
        floor_m=FLOOR_M,
        fascia_m=FASCIA_M,
        eaves=PROMPT_EAVES_M,
    )
    rules += HOME
    heights = scene["terrain"]["heights"]
    site = (
        f"{rules}\nThe site:\n"
        f"- datum: {scene['frame']['datum_m']:.2f} m (NZVD2016); "
        f"ground from {min(heights):.2f} to {max(heights):.2f} m above it.\n"
        f"- parcels on the title (local x, y corners):\n{_rings('parcel', scene['parcels'])}\n"
        f"{frontages}"
    )
    if keep_clear:
        site += f"- areas the owner wants kept clear:\n{_rings('area', keep_clear)}\n"
    if buildings:
        site += f"- existing buildings (keep {MIN_SEPARATION_M:g} m away):\n"
        site += f"{_rings('building', buildings)}\n"
    return site


def _rings(name: str, rings: Sequence[Sequence[Sequence[float]]]) -> str:
    return "\n".join(
        f"  - {name} {i}: " + ", ".join(f"({p[0]:.2f}, {p[1]:.2f})" for p in ring)
        for i, ring in enumerate(rings)
    )


def describe(report: Report) -> str:
    """The evaluator's verdicts as feedback for the next attempt."""
    lines = [f"Evaluator verdict: {report.status}."]
    lines += [f"- {c.name}: {c.status}. {c.detail}" for c in report.checks]
    return "\n".join(lines)


def placing(product: Footprint, roof: str | None = None) -> str:
    """What the brief adds when the owner places a real product: its footprint,
    which the evaluator checks the walls against, and its roof as the supplier
    builds it (``roof``, e.g. "a gable roof at 20°"), where that is known."""
    text = (
        f"Place this real prefab: the {product.name}. Its walls are a "
        f"{product.length_m:g} × {product.width_m:g} m rectangle, measured outside: "
        "the placements offered are its footprint; choose the one that best suits the "
        "brief and the site."
    )
    if roof is None:
        return text
    return f"{text} Give it the roof its supplier builds: {roof}, within the height limit."


def describe_offers(offers: Offers) -> str:
    """The placements offered, numbered, each with its sides and steepest roofs;
    and, for a plan with none, why."""
    lines = [f"- {heading(offers.eaves_m)}. Walls' corners in local x, y:"]
    lines += [
        f"  - {offer.number}: {_offer_text(offer, offers.eaves_m)}" for offer in offers.offers
    ]
    lines += [f"  - {reason}" for reason in offers.missing]
    lines.append("  Choose one of these by its number.")
    return "\n".join(lines) + "\n"


def _offer_text(offer: Offer, eaves_m: float) -> str:
    long_a, short_a, long_b, short_b = offer.sides()
    gable, skillion = (
        steepest_pitch(offer, form, STOREY_WALLS_M, eaves_m) for form in ("gable", "skillion")
    )
    return (
        f"a {offer.length_m:g} × {offer.width_m:g} m plan: {offer.summary}; its long walls "
        f"face {long_a} and {long_b}, its short walls {short_a} and {short_b}. With "
        f"{STOREY_WALLS_M:g} m walls and {eaves_m:g} m eaves, the steepest roof within the "
        f"height limit: a gable or hip at {gable:.1f}°, a skillion rising to a long wall at "
        f"{skillion:.1f}°."
    )
