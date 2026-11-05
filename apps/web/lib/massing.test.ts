import { describe, expect, it } from "vitest";

import { type Placement, parseJob } from "./api";
import { JOB } from "./fixtures";
import { LIVE } from "./fixtures-sites";
import { clearanceWords, fitsWords, massingLayers } from "./massing";

const PLACEMENT: Placement = parseJob({
  ...JOB,
  status: "running",
  live: LIVE,
}).live!.placement!;

describe("the instant massing in words", () => {
  it("says how soon a home of the plan was found to fit, and how far from the boundary", () => {
    expect(fitsWords(PLACEMENT)).toBe(
      "In 2 s: a 10 × 4.8 m home fits here, 2.4 m from the boundary; Muse is now designing it.",
    );
  });

  it("says under a second when it was", () => {
    expect(fitsWords({ ...PLACEMENT, foundInS: 0.06 })).toMatch(
      /^In under a second: a 10 × 4\.8 m home/,
    );
  });

  it("lists each clearance the evaluator measured, and only those", () => {
    expect(clearanceWords(PLACEMENT)).toEqual([
      "2.4 m from the boundary",
      "2.2 m from the section line",
      "6.8 m from the street",
    ]);
    const near = {
      ...PLACEMENT,
      clearances: {
        titleBoundaryM: 3,
        sectionLineM: null,
        buildingM: 2.04,
        streetEdgeM: null,
      },
    };
    expect(clearanceWords(near)).toEqual([
      "3.0 m from the boundary",
      "2.0 m from the nearest building",
    ]);
  });
});

describe("the instant massing on the map", () => {
  it("is its walls and outline as polygons, labelled just below them, clear of the block", () => {
    const layers = massingLayers(PLACEMENT);
    expect(layers.walls.features).toEqual([
      {
        id: "walls",
        properties: null,
        geometry: { type: "Polygon", coordinates: [LIVE.placement.walls] },
      },
    ]);
    expect(layers.outline.features[0].geometry.coordinates).toEqual([
      LIVE.placement.outline,
    ]);
    // Below the walls' middle, at the outline's southernmost point.
    const [lon, lat] = layers.labelAt;
    expect(lon).toBeCloseTo(171.862045, 6);
    expect(lat).toBeCloseTo(-42.1159, 6);
  });
});
