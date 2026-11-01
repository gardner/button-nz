# Textures

The trusted render's finishes for the Dwelling: weatherboard, timber boards,
sheet panels, and two metal roofing profiles. `textures.json` lists them, with
the scale each is shown at.

All of them come from [Poly Haven](https://polyhaven.com/textures) and are
CC0 1.0 (public domain): no attribution is required, but it is given here with
thanks. Each set's page is in `textures.json`.

`scripts/prepare_textures.py` made these 1024 px maps from Poly Haven's 2K
JPEGs:
- `<set>_detail.jpg`: the diffuse map turned greyscale, so the render can tint
  it with the product's colour;
- `<set>_normal.jpg`: the OpenGL normal map.

No supplier photograph, render or drawing is used as a texture.
