"""Real prefab products, as their suppliers publish them (``data/catalogue``).

Every product carries the pages its figures came from. A figure a supplier
doesn't publish stays missing: a price is ``None`` rather than a guess, and
dimensions whose page doesn't say what they measure are marked unlabelled.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

CATALOGUE = Path(__file__).resolve().parents[3] / "data" / "catalogue" / "products.json"
MAX_FLOOR_AREA_M2 = 70.0  # the granny-flat exemption's limit


class CatalogueError(ValueError):
    """A product that breaks the catalogue's rules: never offered."""


class Product(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    id: str
    supplier: str
    model: str
    url: str
    type: str  # transportable, panelised…
    length_m: float  # the published outside footprint
    width_m: float
    dimensions_labelled: bool  # False: the page doesn't say what the figures measure
    floor_area_m2: float  # as the supplier states it
    area_basis: str  # internal, or "not stated"
    bedrooms: int
    bathrooms: int
    price_nzd: int | None  # None: not published
    price_basis: str
    excludes: str
    west_coast: str  # what the supplier says about delivering to the West Coast
    sources: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> Self:
        """A product from its JSON, checked against the catalogue's rules."""
        try:
            return cls.model_validate_json(json.dumps(raw), strict=True)
        except ValidationError as error:
            raise CatalogueError(f"{raw.get('id', '?')}: {error}") from error

    @model_validator(mode="after")
    def _follows_the_rules(self) -> Self:
        problem = _problem(self)
        if problem:
            raise ValueError(problem)
        return self


def _problem(product: Product) -> str | None:
    if not product.sources:
        return "no source for its figures"
    if not all(u.startswith("https://") for u in (product.url, *product.sources)):
        return "every link must be https"
    for name in ("length_m", "width_m", "floor_area_m2"):
        if getattr(product, name) <= 0:
            return f"{name} must be positive"
    if product.floor_area_m2 > MAX_FLOOR_AREA_M2:
        return f"over the exemption's {MAX_FLOOR_AREA_M2:g} m²"
    if (
        product.area_basis == "internal"
        and product.floor_area_m2 >= product.length_m * product.width_m
    ):
        return "an internal area can't fill the outside footprint: check both figures"
    if product.price_nzd is not None and product.price_nzd <= 0:
        return "a price must be positive, or null if not published"
    return None


def load_products(path: Path = CATALOGUE) -> tuple[Product, ...]:
    """Every product in the catalogue at ``path``; one bad product refuses them all."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    products = tuple(Product.parse(p) for p in raw["products"])
    seen: set[str] = set()
    for product in products:
        if product.id in seen:
            raise CatalogueError(f"{product.id} appears twice")
        seen.add(product.id)
    return products
