"""Experiment A's ground truth (plan §11): objective questions about the site's
terrain, answered from the DEM alone, independently of any model.

Heights come from ``terrain_math.height_at`` on the scene's terrain, the same
triangulated surface the model's views and the evaluator use. Points are in
the model's local frame (metres, x east, y north). A question whose answer
would be ambiguous (gentle ground for an aspect, a near tie for the steepest
area) is not asked, so every answer is checkable.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from shapely import Point, Polygon, box, union_all

from button_nz.agent.site import DesignSite
from button_nz.blender_worker.terrain_math import height_at
from button_nz.evaluation import ground_range
from button_nz.geo.geometry import Ring
from button_nz.lidar import inspect_elevation
from button_nz.lidar.analysis import gradients

DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
MIN_GRADE = 0.05  # 1 in 20: gentler ground has no clear downhill direction
SECTOR_MARGIN_DEG = 10.0  # keep aspects this far inside their 45° sector
MIN_HEIGHT_DIFFERENCE_M = 0.3
MIN_SLOPE_LEAD_DEG = 2.0  # the steepest area must lead the next by this much
HEIGHT_TOLERANCE_M = 0.2
RELIEF_TOLERANCE_M = 0.25
AREA_HALF_M = 2.5  # the squares compared for steepness
RELIEF_HALF_M = 5.0
MARGIN_M = 0.5  # keep marks this far inside the title and the measured grid
TRIES_PER_QUESTION = 200


@dataclass(frozen=True)
class Mark:
    """A labelled point (``half_m`` 0) or square drawn on the model's views."""

    label: str
    x: float
    y: float
    half_m: float = 0.0


@dataclass(frozen=True)
class Question:
    id: str
    kind: str  # aspect, height_difference, relief or steepest
    text: str
    marks: tuple[Mark, ...]
    answer: str | float
    choices: tuple[str, ...] = ()
    tolerance: float = 0.0  # for numeric answers, in metres


def generate(site: DesignSite, per_kind: int, seed: int) -> list[Question]:
    """Up to ``per_kind`` questions of each kind, reproducible from ``seed``."""
    terrain = _Terrain(site)
    rng = np.random.default_rng(seed)
    makers: list[tuple[str, Callable[[], Question | None]]] = [
        ("aspect", lambda: _aspect(terrain, rng)),
        ("height_difference", lambda: _height_difference(terrain, rng)),
        ("relief", lambda: _relief(terrain, rng)),
        ("steepest", lambda: _steepest(terrain, rng)),
    ]
    questions: list[Question] = []
    for kind, make in makers:
        found = _take(make, per_kind)
        questions += [
            Question(f"{kind}-{i + 1}", q.kind, q.text, q.marks, q.answer, q.choices, q.tolerance)
            for i, q in enumerate(found)
        ]
    return questions


def score(question: Question, reply: str) -> bool:
    """Whether ``reply`` (just the answer, as asked) is right."""
    text = reply.strip()
    if question.choices:
        return text.upper() == str(question.answer).upper()
    try:
        value = float(text)
    except ValueError:
        return False
    return math.isfinite(value) and abs(value - float(question.answer)) <= question.tolerance


class _Terrain:
    """The scene's surface in local metres, and where marks may go."""

    def __init__(self, site: DesignSite) -> None:
        self.surface = cast("dict[str, Any]", site.scene["terrain"])  # height_at's shape
        self.grid, self.frame = site.context.terrain, site.frame
        self.east, self.north = gradients(self.grid)
        frame = site.frame
        title = union_all([Polygon([frame.to_local(p) for p in r]) for r in site.context.parcels])
        s = self.surface
        x0, y0, cell = float(s["x0"]), float(s["y0"]), float(s["cell_m"])
        cols, rows = int(s["cols"]), int(s["rows"])
        measured = box(x0, y0 - (rows - 1) * cell, x0 + (cols - 1) * cell, y0)
        self.region = title.intersection(measured).buffer(-MARGIN_M)

    def height(self, x: float, y: float) -> float:
        return height_at(self.surface, x, y)

    def place(self, rng: np.random.Generator, half_m: float, label: str) -> Mark | None:
        west, south, east, north = self.region.bounds
        x = round(float(rng.uniform(west, east)), 1)
        y = round(float(rng.uniform(south, north)), 1)
        shape = box(x - half_m, y - half_m, x + half_m, y + half_m) if half_m else Point(x, y)
        return Mark(label, x, y, half_m) if self.region.contains(shape) else None

    def cell_gradient(self, mark: Mark) -> tuple[float, float]:
        """dz/dx and dz/dy of the DEM cell under ``mark``, as the normal map and
        hillshade the model reads compute them (lidar.analysis.gradients)."""
        x, y = self.frame.to_nztm((mark.x, mark.y))
        west, _, _, north = self.grid.bbox
        row, col = int((north - y) // self.grid.cell_m), int((x - west) // self.grid.cell_m)
        return float(self.east[row, col]), float(self.north[row, col])

    def square(self, mark: Mark) -> Ring:
        """``mark``'s square in NZTM, as the tools take it."""
        x, y, h = mark.x, mark.y, mark.half_m
        corners = ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h), (x - h, y - h))
        return tuple(self.frame.to_nztm(c) for c in corners)


def _take(make: Callable[[], Question | None], count: int) -> list[Question]:
    found: list[Question] = []
    for _ in range(TRIES_PER_QUESTION * count):
        if len(found) == count:
            break
        question = make()
        if question is not None:
            found.append(question)
    return found


def _aspect(terrain: _Terrain, rng: np.random.Generator) -> Question | None:
    a = terrain.place(rng, 0.0, "A")
    if a is None:
        return None
    gx, gy = terrain.cell_gradient(a)
    if math.hypot(gx, gy) < MIN_GRADE:
        return None
    bearing = math.degrees(math.atan2(-gx, -gy)) % 360  # downhill, clockwise from north
    sector = round(bearing / 45) % 8
    if abs(bearing - 45 * round(bearing / 45)) > 22.5 - SECTOR_MARGIN_DEG:
        return None
    text = (
        f"Which way does the ground slope down at point A ({a.x:.1f}, {a.y:.1f})? "
        f"Answer with one of: {', '.join(DIRECTIONS)}."
    )
    return Question("", "aspect", text, (a,), DIRECTIONS[sector], DIRECTIONS)


def _height_difference(terrain: _Terrain, rng: np.random.Generator) -> Question | None:
    a, b = terrain.place(rng, 0.0, "A"), terrain.place(rng, 0.0, "B")
    if a is None or b is None or math.hypot(a.x - b.x, a.y - b.y) < 5.0:
        return None
    difference = terrain.height(a.x, a.y) - terrain.height(b.x, b.y)
    if abs(difference) < MIN_HEIGHT_DIFFERENCE_M:
        return None
    text = (
        f"How much higher is the ground at A ({a.x:.1f}, {a.y:.1f}) than at "
        f"B ({b.x:.1f}, {b.y:.1f}), in metres? Answer with a number only, "
        "negative if A is lower."
    )
    return Question("", "height_difference", text, (a, b), difference, (), HEIGHT_TOLERANCE_M)


def _relief(terrain: _Terrain, rng: np.random.Generator) -> Question | None:
    a = terrain.place(rng, RELIEF_HALF_M, "A")
    if a is None:
        return None
    low, high = ground_range(Polygon(terrain.square(a)), terrain.grid)
    text = (
        f"What is the difference between the highest and lowest ground in the "
        f"{2 * RELIEF_HALF_M:g} m square centred on A ({a.x:.1f}, {a.y:.1f}), in metres? "
        "Answer with a number only."
    )
    return Question("", "relief", text, (a,), high - low, (), RELIEF_TOLERANCE_M)


def _steepest(terrain: _Terrain, rng: np.random.Generator) -> Question | None:
    areas = [terrain.place(rng, AREA_HALF_M, label) for label in ("1", "2", "3")]
    if any(a is None for a in areas):
        return None
    marks = tuple(a for a in areas if a is not None)
    if any(_overlap(m, n) for i, m in enumerate(marks) for n in marks[i + 1 :]):
        return None
    slopes = sorted(((_mean_slope(terrain, m), m.label) for m in marks), reverse=True)
    if slopes[0][0] - slopes[1][0] < MIN_SLOPE_LEAD_DEG:
        return None
    centres = ", ".join(f"{m.label} at ({m.x:.1f}, {m.y:.1f})" for m in marks)
    text = (
        f"Which of the {2 * AREA_HALF_M:g} m squares centred on {centres} has the "
        "steepest ground on average? Answer 1, 2 or 3."
    )
    return Question("", "steepest", text, marks, slopes[0][1], ("1", "2", "3"))


def _mean_slope(terrain: _Terrain, mark: Mark) -> float:
    """The square's mean slope exactly as the model's tools report it
    (inspect_elevation's mean_slope_deg over the cell centres inside)."""
    return inspect_elevation(terrain.grid, terrain.square(mark))["mean_slope_deg"]


def _overlap(m: Mark, n: Mark) -> bool:
    gap = 1.0  # at least a metre between squares
    return abs(m.x - n.x) < m.half_m + n.half_m + gap and abs(m.y - n.y) < m.half_m + n.half_m + gap
