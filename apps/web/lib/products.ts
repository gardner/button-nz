/**
 * The real prefab homes that fit inside an accepted design
 * (`button_nz.api.products`), as their suppliers publish them. A price a
 * supplier doesn't publish stays null: it is never estimated.
 */

import {
  ApiError,
  asText,
  list,
  number,
  optional,
  record,
  text,
} from "./fields";

export interface Product {
  id: string;
  supplier: string;
  model: string;
  url: string;
  type: string;
  lengthM: number; // the published outside footprint
  widthM: number;
  floorAreaM2: number; // as the supplier states it
  areaBasis: string;
  bedrooms: number;
  bathrooms: number;
  priceNzd: number | null; // null: not published
  priceBasis: string;
  excludes: string;
  westCoast: string; // what the supplier says about delivering to the West Coast
  sources: string[];
}

export interface Products {
  footprintM2: number;
  fits: Product[]; // largest first
  unchecked: Product[]; // dimensions unlabelled: never shown as fitting
  basis: string; // what fitting does and doesn't check
}

export function parseProducts(raw: unknown): Products {
  const products = record(raw, "products");
  return {
    footprintM2: number(products, "footprint_m2"),
    fits: list(products, "fits").map(parseProduct),
    unchecked: list(products, "unchecked").map(parseProduct),
    basis: text(products, "basis"),
  };
}

function parseProduct(raw: unknown): Product {
  const product = record(raw, "product");
  return {
    id: text(product, "id"),
    supplier: text(product, "supplier"),
    model: text(product, "model"),
    url: link(product.url),
    type: text(product, "type"),
    lengthM: number(product, "length_m"),
    widthM: number(product, "width_m"),
    floorAreaM2: number(product, "floor_area_m2"),
    areaBasis: text(product, "area_basis"),
    bedrooms: number(product, "bedrooms"),
    bathrooms: number(product, "bathrooms"),
    priceNzd: optional(product, "price_nzd", number),
    priceBasis: text(product, "price_basis"),
    excludes: text(product, "excludes"),
    westCoast: text(product, "west_coast"),
    sources: list(product, "sources").map(link),
  };
}

/** A supplier's page, shown as a link: only https, never a script. */
function link(value: unknown): string {
  const url = asText(value, "link");
  if (!url.startsWith("https://"))
    throw new ApiError(`expected an https link, not ${JSON.stringify(url)}`);
  return url;
}
