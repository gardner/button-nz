import { describe, expect, it } from "vitest";

import { ApiError } from "./fields";
import { TOWN } from "./fixtures-sites";
import { boundsOf, parseCollection } from "./geo";

describe("parseCollection", () => {
  it("reads a FeatureCollection, keeping each feature's properties as read", () => {
    const town = parseCollection(TOWN, "town", (p) => p.category);
    expect(town.features.map((f) => f.properties)).toEqual([
      "clear",
      "outlines",
      "none",
    ]);
    expect(town.features[0].geometry.type).toBe("Polygon");
  });

  it.each([
    [{ type: "Feature" }],
    [{ type: "FeatureCollection", features: [{ geometry: null }] }],
    [
      {
        type: "FeatureCollection",
        features: [
          { properties: {}, geometry: { type: "Circle", coordinates: [] } },
        ],
      },
    ],
    [
      {
        type: "FeatureCollection",
        features: [
          {
            properties: {},
            geometry: { type: "Polygon", coordinates: [[[171, "-42"]]] },
          },
        ],
      },
    ],
  ])("refuses a collection it can't draw", (raw) => {
    expect(() => parseCollection(raw, "layer", () => null)).toThrow(ApiError);
  });
});

describe("boundsOf", () => {
  it("is the west, south, east and north of every position", () => {
    const town = parseCollection(TOWN, "town", () => null);
    expect(boundsOf(town)).toEqual([171.86, -42.116, 171.8622, -42.1158]);
  });

  it("is null for an empty collection", () => {
    expect(
      boundsOf(
        parseCollection(
          { type: "FeatureCollection", features: [] },
          "x",
          () => null,
        ),
      ),
    ).toBeNull();
  });
});
