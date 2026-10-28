"""The evaluator's inputs and verdicts. Verdicts are immutable: nothing,
including the design agent, can turn a failed check into a pass."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

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
    preservation_areas: tuple[Ring, ...] = ()  # the owner's areas to keep clear
