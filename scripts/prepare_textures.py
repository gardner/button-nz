"""Prepare the CC0 textures the trusted render uses, from Poly Haven's 2K sets.

    uv run python scripts/prepare_textures.py inbox/textures

For each set in ``src/button_nz/blender_worker/textures/textures.json`` this
writes two 1024 px JPEGs next to it:

- ``<set>_detail.jpg``: the diffuse map as greyscale detail whose mean is
  ``MEAN`` in linear light, so the render, tinting it with the product's
  colour, shows that colour with the material's grain and shading;
- ``<set>_normal.jpg``: the OpenGL normal map.
"""

import json
import sys
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

TEXTURES = Path(__file__).resolve().parents[1] / "src" / "button_nz" / "blender_worker" / "textures"
SIZE = 1024
MEAN = 0.85  # the detail's mean in linear light: bright, with headroom for its highlights
CONTRAST = 0.6  # of the photograph's: grime and stains softened; the normal map keeps the relief


def main(source: Path) -> None:
    sets: dict[str, object] = json.loads((TEXTURES / "textures.json").read_text())["sets"]
    for name in sets:
        diffuse = Image.open(source / name / f"{name}_diffuse_2k.jpg").convert("RGB")
        detail(diffuse).save(TEXTURES / f"{name}_detail.jpg", quality=90)
        normal = Image.open(source / name / f"{name}_nor_gl_2k.jpg").convert("RGB")
        normal.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(
            TEXTURES / f"{name}_normal.jpg", quality=90
        )
        print(name)


def detail(diffuse: Image.Image) -> Image.Image:
    """``diffuse`` as greyscale detail at ``SIZE``: its linear mean ``MEAN``, its
    variation ``CONTRAST`` of the photograph's."""
    srgb = np.asarray(diffuse.resize((SIZE, SIZE), Image.Resampling.LANCZOS)) / 255.0
    linear = _to_linear(srgb) @ np.array([0.2126, 0.7152, 0.0722])  # luminance
    relative = linear / linear.mean()
    scaled = np.clip(MEAN * (1 + CONTRAST * (relative - 1)), 0.0, 1.0)
    return Image.fromarray(np.round(_to_srgb(scaled) * 255).astype(np.uint8), mode="L")


def _to_linear(c: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb(c: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
