"""Prefab product catalogue and matching."""

from button_nz.catalogue.fit import Matches, fits, matches, placement
from button_nz.catalogue.products import CATALOGUE, CatalogueError, Product, load_products

__all__ = [
    "CATALOGUE",
    "CatalogueError",
    "Matches",
    "Product",
    "fits",
    "load_products",
    "matches",
    "placement",
]
