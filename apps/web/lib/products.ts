/**
 * The real prefab homes that fit inside an accepted design
 * (`button_nz.api.products`), as their suppliers publish them. A price a
 * supplier doesn't publish stays null: it is never estimated.
 */

import {
  ApiError,
  asList,
  asText,
  type Fields,
  flag,
  list,
  number,
  oneOf,
  optional,
  record,
  text,
} from "./fields";
import { type FeatureCollection, parseCollection } from "./geo";

export const ROOF_FORMS = ["mono", "gable", "hip", "flat"] as const;
export type RoofForm = (typeof ROOF_FORMS)[number];

/** How a product looks, from its supplier's material: the roof forms it
 * comes with (the one its material shows first), the pitch where published,
 * and its wall and roof colours, as `#rrggbb`. */
export interface Appearance {
  roofForms: RoofForm[];
  roofPitchDeg: number | null; // null: not published
  walls: string;
  roof: string;
}

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
  appearance: Appearance;
  placeable: boolean; // its footprint is a known rectangle: it can be placed on a site
  placedFootprint: FeatureCollection<null> | null; // where it would stand in the walls, if sent
}

/** A product that fits the walls but can stand nowhere on the site within
 * the floor-level rule: never shown as fitting. */
export interface Unplaceable {
  product: Product;
  reason: string;
}

export interface Products {
  footprintM2: number;
  fits: Product[]; // largest first
  unchecked: Product[]; // dimensions unlabelled: never shown as fitting
  unplaceable: Unplaceable[];
  basis: string; // what fitting does and doesn't check
}

export function parseProducts(raw: unknown): Products {
  const products = record(raw, "products");
  return {
    footprintM2: number(products, "footprint_m2"),
    fits: list(products, "fits").map(parseProduct),
    unchecked: list(products, "unchecked").map(parseProduct),
    unplaceable: list(products, "unplaceable").map((raw) => ({
      product: parseProduct(raw),
      reason: text(record(raw, "unplaceable product"), "reason"),
    })),
    basis: text(products, "basis"),
  };
}

/** The whole catalogue (GET /products), as catalogued. */
export function parseCatalogue(raw: unknown): Product[] {
  return asList(raw, "catalogue").map(parseProduct);
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
    appearance: appearance(record(product.appearance, "appearance")),
    placeable: flag(product, "placeable"),
    placedFootprint:
      product.placed_footprint == null // absent today; null where none was placed
        ? null
        : parseCollection(
            product.placed_footprint,
            "placed footprint",
            () => null,
          ),
  };
}

function appearance(looks: Fields): Appearance {
  return {
    roofForms: list(looks, "roof_forms").map((form) =>
      oneOf({ roof_form: form }, "roof_form", ROOF_FORMS),
    ),
    roofPitchDeg: optional(looks, "roof_pitch_deg", number),
    walls: colour(looks, "walls"),
    roof: colour(looks, "roof"),
  };
}

/** A colour, only ever as `#rrggbb`: it is painted into an SVG. */
function colour(fields: Fields, key: string): string {
  const value = text(fields, key);
  if (!/^#[0-9a-fA-F]{6}$/.test(value))
    throw new ApiError(`expected ${key} to be a #rrggbb colour`);
  return value;
}

/** A supplier's page, shown as a link: only https, never a script. */
function link(value: unknown): string {
  const url = asText(value, "link");
  if (!url.startsWith("https://"))
    throw new ApiError(`expected an https link, not ${JSON.stringify(url)}`);
  return url;
}
