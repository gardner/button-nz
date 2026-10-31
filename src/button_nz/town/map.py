"""The town screen's map: each section coloured by whether a real prefab
fits on it, with the eave allowance. It draws parcel and building outlines
only: no aerial imagery, no addresses."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry.base import BaseGeometry

from button_nz.geo.geometry import BBox
from button_nz.town.screen import SectionResult, polygons

type RGB = tuple[int, int, int]

COLOURS: dict[str, RGB] = {
    "clear": (46, 125, 50),  # fits clear of everything over 2 m on the LiDAR
    "outlines_only": (240, 165, 0),  # fits under the LINZ outlines, not clear today
    "none": (210, 210, 210),  # no product fits
    "building": (60, 60, 60),
    "edge": (255, 255, 255),
    "background": (255, 255, 255),
    "text": (30, 30, 30),
}
LEGEND = (
    ("clear", "A real prefab fits, clear of everything over 2 m on the LiDAR"),
    ("outlines_only", "Fits under the LINZ building outlines, but not clear today"),
    ("none", "No prefab in the catalogue fits"),
    ("building", "LINZ building outline (2015–16)"),
)


def colour_of(result: SectionResult) -> str:
    """The legend entry for ``result``, with the eave allowance."""
    if result.clear_eaves:
        return "clear"
    return "outlines_only" if result.fits_eaves else "none"


def draw_map(
    results: Sequence[SectionResult],
    shapes: Mapping[int, BaseGeometry],
    buildings: Sequence[BaseGeometry],
    bbox: BBox,
    path: Path,
    title: str = "",
    notes: Sequence[str] = (),
    width_px: int = 2000,
) -> Path:
    """Draw ``bbox`` with each result's section from ``shapes`` (by ParcelID)
    and the ``buildings``, then a legend below; write a PNG to ``path``."""
    scale = width_px / (bbox[2] - bbox[0])
    map_height = round((bbox[3] - bbox[1]) * scale)
    size = max(12, width_px // 70)
    font = ImageFont.load_default(size=size)
    line = round(size * 1.5)
    legend_height = line * (len(LEGEND) + len(notes) + 3)
    image = Image.new("RGB", (width_px, map_height + legend_height), COLOURS["background"])
    draw = ImageDraw.Draw(image)

    def pixels(ring: Iterable[tuple[float, ...]]) -> list[tuple[float, float]]:
        return [((x - bbox[0]) * scale, (bbox[3] - y) * scale) for x, y, *_ in ring]

    def fill(geometry: BaseGeometry, colour: RGB, edge: RGB | None) -> None:
        for part in polygons(geometry):
            draw.polygon(pixels(part.exterior.coords), fill=colour, outline=edge)
            for hole in part.interiors:
                draw.polygon(pixels(hole.coords), fill=COLOURS["background"], outline=edge)

    for result in results:
        if result.parcel_id in shapes:
            fill(shapes[result.parcel_id], COLOURS[colour_of(result)], COLOURS["edge"])
    for building in buildings:
        fill(building, COLOURS["building"], None)
    _legend(draw, font, map_height, line, title, notes)
    image.save(path, format="PNG", optimize=True)
    return path


def _legend(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    top: int,
    line: int,
    title: str,
    notes: Sequence[str],
) -> None:
    x, y = line, top + line // 2
    draw.text((x, y), title, fill=COLOURS["text"], font=font)
    for name, label in LEGEND:
        y += line
        draw.rectangle((x, y + 2, x + line - 4, y + line - 6), fill=COLOURS[name])
        draw.text((x + line + 6, y), label, fill=COLOURS["text"], font=font)
    for note in notes:
        y += line
        draw.text((x, y), note, fill=COLOURS["text"], font=font)
