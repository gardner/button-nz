"""Turn what Blender measured of the model's ``Dwelling`` into a Proposal.

The evaluator only ever sees geometry measured from the built scene, never the
model's description of it. Problems with the model's script (an exception, no
``Dwelling``, a footprint in pieces) are ``DesignError``s: feedback for the
model's next attempt, not crashes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from shapely import MultiPolygon, Polygon, union_all

from button_nz.evaluation import Proposal
from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring


class DesignError(ValueError):
    """The model's script did not produce a measurable dwelling."""


@dataclass(frozen=True)
class Measurements:
    """What ``run_design.py`` measured, in the scene's local frame."""

    error: str | None
    footprint: Ring | None  # outer ring of the Dwelling's faces projected onto XY
    parts: int  # connected pieces of that footprint
    z_min: float | None  # relative to the scene datum
    z_max: float | None
    floor_area_m2: float | None
    storeys: int | None


def parse_measurements(raw: Mapping[str, Any]) -> Measurements:
    """Parse ``measurements.json``, joining the Dwelling's projected faces into
    its footprint (Blender's Python has no shapely, so the union is done here)."""
    faces = cast("list[list[list[float]]] | None", raw.get("faces_xy"))
    footprint, parts = _footprint(faces) if faces else (None, 0)
    return Measurements(
        error=cast("str | None", raw.get("error")),
        footprint=footprint,
        parts=parts,
        z_min=_optional_float(raw.get("z_min")),
        z_max=_optional_float(raw.get("z_max")),
        floor_area_m2=_optional_float(raw.get("floor_area_m2")),
        storeys=None if raw.get("storeys") is None else int(cast("int", raw["storeys"])),
    )


def to_proposal(measurements: Measurements, frame: LocalFrame, datum_m: float) -> Proposal:
    """The NZTM/NZVD2016 proposal for ``measurements``."""
    if measurements.error:
        raise DesignError(f"Your script raised an error:\n{measurements.error}")
    if measurements.parts > 1:
        raise DesignError(
            f"The Dwelling's footprint is in {measurements.parts} pieces; "
            "it must be one connected footprint."
        )
    if measurements.footprint is None or measurements.z_min is None or measurements.z_max is None:
        raise DesignError("Your script did not create a mesh object named 'Dwelling'.")
    return Proposal(
        footprint=tuple(frame.to_nztm(point) for point in measurements.footprint),
        floor_level_m=datum_m + measurements.z_min,
        height_above_floor_m=measurements.z_max - measurements.z_min,
        floor_area_m2=measurements.floor_area_m2,
        storeys=measurements.storeys,
    )


def _footprint(faces: list[list[list[float]]]) -> tuple[Ring | None, int]:
    polygons = [Polygon(face) for face in faces if len(face) >= 3]
    union = union_all([p for p in polygons if p.is_valid and p.area > 1e-9])
    if union.is_empty:
        return None, 0
    if isinstance(union, MultiPolygon):
        return None, len(union.geoms)
    if not isinstance(union, Polygon):
        return None, 0
    outline = union.simplify(1e-6)
    if not isinstance(outline, Polygon):
        return None, 0
    return tuple((float(x), float(y)) for x, y in outline.exterior.coords), 1


def _optional_float(value: object) -> float | None:
    return None if value is None else float(cast("float", value))
