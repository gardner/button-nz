"""LINZ tile names to NZTM2000 bounds.

LINZ names elevation and imagery tiles on the Topo50 grid as
``<sheet>_<scale>_<row><col>``, e.g. ``BS21_1000_4730``. A sheet is 24 km wide
and 36 km tall; at a given scale it splits into ``50000 / scale`` cells per
side, numbered from 1 at the top left. Deriving bounds from the name means a
tile's footprint can never drift from the tile it names.
"""

import re

type BBox = tuple[float, float, float, float]

_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O
_SHEET_WIDTH = 24_000.0
_SHEET_HEIGHT = 36_000.0
_SCALES = {500, 1000, 2000, 5000, 10000, 50000}
_NAME = re.compile(r"([A-HJ-NP-Z]{2})(\d{2})_(\d+)_(\d+)")


def tile_bounds(name: str) -> BBox:
    """The NZTM2000 bounds (minx, miny, maxx, maxy) of LINZ tile ``name``."""
    match = _NAME.fullmatch(name)
    scale = int(match.group(3)) if match else 0
    if match is None or scale not in _SCALES:
        raise ValueError(f"not a LINZ tile name: {name!r}")
    letters, sheet_col, _, index = match.groups()
    cells = 50_000 // scale
    digits = len(index) // 2
    row, col = int(index[:digits]), int(index[digits:])
    if len(index) != 2 * digits or not (1 <= row <= cells and 1 <= col <= cells):
        raise ValueError(f"not a LINZ tile name: {name!r}")
    sheet_row = 24 * _LETTERS.index(letters[0]) + _LETTERS.index(letters[1]) - 16
    left = 988_000.0 + int(sheet_col) * _SHEET_WIDTH
    top = 6_234_000.0 - sheet_row * _SHEET_HEIGHT
    width, height = _SHEET_WIDTH / cells, _SHEET_HEIGHT / cells
    return (
        left + (col - 1) * width,
        top - row * height,
        left + col * width,
        top - (row - 1) * height,
    )
