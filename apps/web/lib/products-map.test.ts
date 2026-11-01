import { describe, expect, it } from "vitest";

import { ApiError } from "./fields";
import { PRODUCTS } from "./fixtures";
import { parseProducts } from "./products";

const FOOTPRINT = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {},
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [171.862, -42.1159],
            [171.8621, -42.1159],
            [171.8621, -42.11585],
            [171.862, -42.1159],
          ],
        ],
      },
    },
  ],
};

describe("a product's place in the walls", () => {
  it("reads where a fitting product would stand", () => {
    const raw = {
      ...PRODUCTS,
      fits: [{ ...PRODUCTS.fits[0], placed_footprint: FOOTPRINT }],
    };
    const [vista] = parseProducts(raw).fits;
    expect(vista.placedFootprint?.features).toHaveLength(1);
  });

  it("has none where the API doesn't send it", () => {
    expect(parseProducts(PRODUCTS).fits[0].placedFootprint).toBeNull();
  });

  it("refuses a footprint it can't draw", () => {
    const raw = {
      ...PRODUCTS,
      fits: [{ ...PRODUCTS.fits[0], placed_footprint: { type: "Feature" } }],
    };
    expect(() => parseProducts(raw)).toThrow(ApiError);
  });
});
