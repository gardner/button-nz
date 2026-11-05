"""Design specs for tests with a fake Blender runner: each name is a spec that
builds on placement 1 of a flat site at the datum, and the runner, reading the
spec back from the built script, returns that name's stand-in measurements.
The names differ only in their walls' height."""

import json

from button_nz.agent.spec import parse_spec, spec_json

NAMES = ("good", "near", "broken", "off", "split", "inside", "deck")


def spec(name: str, placement: int = 1) -> str:
    """The spec named ``name``, as the model sends it."""
    raw = {
        "placement": placement,
        "floor_z_m": 0.3,
        "wall_height_m": 2.1 + 0.1 * NAMES.index(name),
        "roof": {"form": "flat", "pitch_deg": 0},
        "eaves_m": 0.3,
    }
    return json.dumps(raw)


def name_of(script: str) -> str:
    """The name of the spec ``script`` was built from (its second line)."""
    built = script.splitlines()[1].removeprefix("# ")
    for name in NAMES:
        if spec_json(parse_spec(spec(name))) == built:
            return name
    raise ValueError(f"no named spec built {built}")
