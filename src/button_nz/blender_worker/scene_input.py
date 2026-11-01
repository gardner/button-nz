"""The plain-JSON scene description handed to headless Blender.

Raster work (rasterio, pyproj) stays outside Blender; Blender's script only
reads this JSON. Everything is in a local metre frame (``LocalFrame``) so the
scene never carries seven-digit NZTM coordinates. Heights are relative to
``frame.datum_m`` (NZVD2016 metres), so absolute heights stay recoverable.
"""

from collections.abc import Sequence
from typing import Literal, NotRequired, TypedDict

from button_nz.geo.crs import LocalFrame
from button_nz.geo.geometry import Ring
from button_nz.geo.terrain import TerrainGrid


class Frame(TypedDict):
    origin_nztm: list[float]
    crs: str
    vertical_crs: str
    datum_m: float


class HeightGrid(TypedDict):
    """``rows`` x ``cols`` samples at cell centres, row-major from the north
    edge. ``(x0, y0)`` is the north-west sample; x grows east, y north."""

    rows: int
    cols: int
    cell_m: float
    x0: float
    y0: float
    heights: list[float]


# The CC0 texture sets in blender_worker/textures (textures.json describes them).
TextureName = Literal[
    "white_planks_clean",
    "japanese_cedar_planks",
    "groove_panel",
    "box_profile_metal_sheet",
    "corrugated_iron",
]


class Finish(TypedDict):
    """A surface of the Dwelling in the trusted render: a linear RGBA colour
    over a texture."""

    rgba: list[float]
    texture: TextureName


class DwellingFinishes(TypedDict):
    """The trusted render's finishes for the Dwelling: its roof (level faces
    in its upper half) and its walls (the rest). Set by the host, never by the
    model."""

    walls: Finish
    roof: Finish


# Bespoke designs: warm white weatherboard, a dark grey corrugated roof.
DEFAULT_FINISHES: DwellingFinishes = {
    "walls": {"rgba": [0.8, 0.75, 0.65, 1.0], "texture": "white_planks_clean"},
    "roof": {"rgba": [0.06, 0.07, 0.08, 1.0], "texture": "corrugated_iron"},
}


class SceneInput(TypedDict):
    frame: Frame
    terrain: HeightGrid
    ndsm: HeightGrid
    parcels: list[list[list[float]]]
    sources: list[str]
    dwelling_finishes: NotRequired[DwellingFinishes]


def with_finishes(scene: SceneInput, finishes: DwellingFinishes) -> SceneInput:
    """``scene`` with the Dwelling's render finishes."""
    return {**scene, "dwelling_finishes": finishes}


def scene_input(
    grid: TerrainGrid,
    frame: LocalFrame,
    parcels: Sequence[Ring],
    datum_m: float | None = None,
) -> SceneInput:
    """Describe ``grid`` and ``parcels`` in ``frame``. ``datum_m`` defaults to
    the lowest ground height, so the terrain starts near z = 0."""
    datum = float(grid.dem.min()) if datum_m is None else datum_m
    x0, y0 = frame.to_local((grid.bbox[0] + grid.cell_m / 2, grid.bbox[3] - grid.cell_m / 2))
    rows, cols = (int(n) for n in grid.dem.shape)

    def heights(values: list[float]) -> HeightGrid:
        return {
            "rows": rows,
            "cols": cols,
            "cell_m": grid.cell_m,
            "x0": x0,
            "y0": y0,
            "heights": values,
        }

    return {
        "frame": {
            "origin_nztm": [frame.origin[0], frame.origin[1]],
            "crs": "EPSG:2193",
            "vertical_crs": "EPSG:7839",
            "datum_m": datum,
        },
        "terrain": heights([float(v) - datum for v in grid.dem.ravel()]),
        "ndsm": heights([float(v) for v in grid.ndsm.ravel()]),
        "parcels": [[list(frame.to_local(point)) for point in ring] for ring in parcels],
        "sources": list(grid.sources),
    }
