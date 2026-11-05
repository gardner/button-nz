"""The design Muse proposes: a placement it was offered and a few parameters,
never geometry. ``agent.build`` builds it and the evaluator checks what was built.

A spec is strict: unknown fields, strings for numbers and values outside the
ranges below are refused, with the reason, as feedback for the model's next
attempt. What depends on the placement (its floor range, its sides, the
height the roof reaches) is checked by ``agent.build.check``.
"""

from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from button_nz.agent.placement import PROMPT_EAVES_M

__all__ = [
    "TOOL",
    "Deck",
    "DesignSpec",
    "Openings",
    "Roof",
    "Side",
    "SpecError",
    "parse_spec",
    "spec_json",
    "spec_tool",
]

TOOL = "propose_design"
# The compass point a wall faces: each offered placement names its four.
type Side = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
PITCHES: dict[str, tuple[float, float]] = {  # degrees, each form's range
    "gable": (10.0, 45.0),
    "hip": (10.0, 45.0),
    "skillion": (3.0, 30.0),
    "flat": (0.0, 0.0),
}


class SpecError(ValueError):
    """A spec that can't be built: feedback for the model, not a crash."""


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Roof(_Strict):
    form: Literal["gable", "hip", "skillion", "flat"] = Field(
        description="gable and hip: the ridge runs along the long walls; skillion: one "
        "slope up to high_side; flat: level"
    )
    pitch_deg: float = Field(
        description="gable and hip 10 to 45, skillion 3 to 30, flat 0", ge=0.0, le=45.0
    )
    high_side: Side | None = Field(
        None, description="skillion only: the side whose wall the roof rises to"
    )

    @model_validator(mode="after")
    def _in_range(self) -> Self:
        low, high = PITCHES[self.form]
        if not low <= self.pitch_deg <= high:
            raise ValueError(f"a {self.form} roof's pitch is {low:g} to {high:g}°")
        if (self.form == "skillion") != (self.high_side is not None):
            raise ValueError("high_side is given for a skillion roof, and only for one")
        return self


class Deck(_Strict):
    side: Side = Field(description="the wall it is beside")
    depth_m: float = Field(description="out from that wall", ge=1.0, le=3.0)
    width_m: float | None = Field(
        None, description="along the wall, centred on it; omit for the whole wall", gt=0.0
    )


class Openings(_Strict):
    side: Side
    windows: int = Field(0, ge=0, le=12)
    doors: int = Field(0, ge=0, le=3)


class DesignSpec(_Strict):
    """One design: where (an offered placement), how high, and its roof."""

    placement: int = Field(description="the number of an offered placement", ge=1)
    floor_z_m: float = Field(
        description="the floor's underside, scene z, within that placement's range"
    )
    wall_height_m: float = Field(2.4, description="floor to the top of the walls", ge=2.1, le=3.0)
    roof: Roof
    eaves_m: float = Field(
        description="how far the roof overhangs the walls", ge=0.0, le=PROMPT_EAVES_M
    )
    deck: Deck | None = Field(None, description="a thin slab level with the floor")
    openings: list[Openings] = Field(
        default_factory=list[Openings],
        description="windows and doors on each side: kept with the design for the "
        "illustration, not cut into the massing model",
    )

    @model_validator(mode="after")
    def _sides_once(self) -> Self:
        sides = [o.side for o in self.openings]
        if len(set(sides)) != len(sides):
            raise ValueError("give each side's openings once")
        return self


def parse_spec(text: str) -> DesignSpec:
    """The spec in ``text`` (JSON); a ``SpecError`` saying what is wrong if it isn't one."""
    try:
        return DesignSpec.model_validate_json(text)
    except ValidationError as error:
        problems = "; ".join(_problem(e) for e in error.errors(include_url=False))
        raise SpecError(f"The design spec was refused: {problems}.") from error


def _problem(error: Any) -> str:
    where = ".".join(str(part) for part in error["loc"])
    message = str(error["msg"]).removeprefix("Value error, ")
    if error["type"] == "json_invalid":
        return f"it is not valid JSON ({message})"
    return f"{where}: {message}" if where else message


def spec_tool() -> dict[str, Any]:
    """The ``propose_design`` tool: its parameters are the spec's JSON schema,
    references inlined (one self-contained object)."""
    schema = DesignSpec.model_json_schema()
    definitions = cast(dict[str, Any], schema.pop("$defs", {}))
    return {
        "type": "function",
        "function": {
            "name": TOOL,
            "description": "Propose the design: an offered placement and its parameters. "
            "It is built in Blender and checked by the evaluator.",
            "parameters": _inlined(schema, definitions),
        },
    }


def _inlined(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        mapping = cast(dict[str, Any], node)
        ref = mapping.get("$ref")
        if isinstance(ref, str):
            return _inlined(definitions[ref.rsplit("/", 1)[-1]], definitions)
        return {k: _inlined(v, definitions) for k, v in mapping.items()}
    if isinstance(node, list):
        return [_inlined(v, definitions) for v in cast(list[Any], node)]
    return node


def spec_json(spec: DesignSpec) -> str:
    """``spec`` as compact JSON, as the model sends it and the trace keeps it."""
    return spec.model_dump_json(exclude_defaults=True)
