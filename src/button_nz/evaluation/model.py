"""The evaluator's inputs and verdicts. Verdicts are immutable: nothing,
including the design agent, can turn a failed check into a pass."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # not verifiable from what we know; never assumed to pass


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str
    measured: Mapping[str, float]
    rule: str

    def __post_init__(self) -> None:
        # A read-only copy, so the evidence behind a verdict can't be edited later.
        object.__setattr__(self, "measured", MappingProxyType(dict(self.measured)))


@dataclass(frozen=True)
class Report:
    checks: tuple[Check, ...]

    @property
    def status(self) -> Status:
        """Any failure fails the report; otherwise any unknown makes it unknown."""
        statuses = {c.status for c in self.checks}
        for status in (Status.FAIL, Status.UNKNOWN):
            if status in statuses:
                return status
        return Status.PASS


@dataclass(frozen=True)
class Proposal:
    """A proposed dwelling. Fields left as None make their checks unknown."""

    footprint: Ring  # NZTM, the outside of the external walls
    floor_level_m: float | None = None  # NZVD2016
    height_above_floor_m: float | None = None
    floor_area_m2: float | None = None  # internal, as the exemption measures it
    storeys: int | None = None


@dataclass(frozen=True)
class SiteContext:
    parcels: tuple[Ring, ...]  # every parcel on the title, NZTM
    terrain: TerrainGrid
    confirmed_buildings: tuple[Ring, ...] = ()  # owner-confirmed residential buildings
    buildings_confirmed: bool = False  # the owner says that list is complete (even if empty)
    preservation_areas: tuple[Ring, ...] = ()  # the owner's areas to keep clear


class InvalidProposal(ValueError):
    """A proposal with impossible values (non-finite, non-positive) or outside
    the measured terrain: it can't be evaluated, so it is never passed."""


def validate(proposal: Proposal) -> None:
    for name in ("floor_level_m", "height_above_floor_m", "floor_area_m2"):
        value = getattr(proposal, name)
        if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
            raise InvalidProposal(f"{name} must be a finite number, not {value}")
    for name in ("height_above_floor_m", "floor_area_m2"):
        value = getattr(proposal, name)
        if value is not None and value <= 0:
            raise InvalidProposal(f"{name} must be positive, not {value}")
    storeys = proposal.storeys
    if storeys is not None and (isinstance(storeys, bool) or storeys < 1):
        raise InvalidProposal(f"storeys must be a whole number of at least 1, not {storeys}")
