"""What the design model is told: the scene contract, the rules it is checked
against, the site in its local frame, and each attempt's verdicts."""

from collections.abc import Sequence

from button_nz.blender_worker.scene_input import SceneInput
from button_nz.evaluation import Report
from button_nz.evaluation.checks import (
    MAX_FLOOR_ABOVE_GROUND_M,
    MAX_FLOOR_AREA_M2,
    MAX_HEIGHT_ABOVE_FLOOR_M,
    MIN_SEPARATION_M,
)
from button_nz.geo.geometry import Ring

CONTRACT = """You design a small detached dwelling on a real New Zealand property by \
writing Blender Python (bpy) scripts. Each script runs in a scene that already holds \
the site; call the run_blender_script tool with the complete script.

Scene contract:
- Units are metres in a local frame: x east, y north, z up. z is relative to the \
datum below.
- Create exactly one mesh object named "Dwelling" whose geometry is the building's \
outside envelope: a closed, solid mesh with a roof over its walls (no doors or \
windows cut through it) whose \
lowest point is the underside of a floor \
spanning its walls (no piles or steps below it). Put all building geometry \
(walls, roof, decks, eaves) in that one mesh: other geometry is rejected. Model a \
deck as a thin slab with posts or balusters, not a solid block: anything solid \
1 m above the floor counts as walls. Floor area is measured inside the walls, \
1 m above the floor; setbacks from everything the building covers, eaves included. \
Changes to the site and other objects (lights, cameras) are discarded.
- Set Dwelling["floor_area_m2"] to the internal floor area and \
Dwelling["storeys"] to the number of storeys.
- Your script can use `bpy`, `math` and `scene` (the scene description, including \
the terrain heights: scene["terrain"]).
- Do not delete or change the site objects (Terrain, AboveGround, Parcel.*).

An independent evaluator measures the Dwelling you build and checks it. You cannot \
argue with a check; change the design instead. Checks, from Schedule 1A of the \
Building Act 2004 (the granny flats exemption):
- inside the title's parcels;
- at least {sep:g} m from the title boundary, from internal section lines \
(reported as unknown if closer: their legal status is unconfirmed) and from \
confirmed residential buildings;
- internal floor area at most {area:g} m²; single storey; at most {height:g} m \
above the floor;
- floor at most {floor:g} m above the lowest ground under the footprint, and not \
below the highest;
- clear of the owner's preservation areas.
"Unknown" means it could not be verified; it is reported, never treated as a pass.
"""


def system_prompt(
    scene: SceneInput, keep_clear: Sequence[Ring] = (), buildings: Sequence[Ring] = ()
) -> str:
    """The contract and the site. ``keep_clear`` (the owner's preservation areas)
    and ``buildings`` (existing ones the owner listed) are local rings."""
    rules = CONTRACT.format(
        sep=MIN_SEPARATION_M,
        area=MAX_FLOOR_AREA_M2,
        height=MAX_HEIGHT_ABOVE_FLOOR_M,
        floor=MAX_FLOOR_ABOVE_GROUND_M,
    )
    heights = scene["terrain"]["heights"]
    site = (
        f"{rules}\nThe site:\n"
        f"- datum: {scene['frame']['datum_m']:.2f} m (NZVD2016); "
        f"ground from {min(heights):.2f} to {max(heights):.2f} m above it.\n"
        f"- parcels on the title (local x, y corners):\n{_rings('parcel', scene['parcels'])}\n"
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
