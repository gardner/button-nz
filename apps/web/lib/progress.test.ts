import { describe, expect, it } from "vitest";

import { ApiError } from "./fields";
import { parseProgress, placed, ringPath, squareFrame } from "./progress";

const EMPTY = {
  frame: null,
  parcels: [],
  buildings: [],
  terrain: null,
  aerial: null,
  survey: null,
};

const RING = [
  [1010, 2010],
  [1020, 2010],
  [1020, 2020],
  [1010, 2010],
];

describe("parseProgress", () => {
  it("reads a build that has shown nothing yet", () => {
    expect(parseProgress(EMPTY)).toEqual({
      frame: null,
      parcels: [],
      buildings: [],
      terrain: null,
      aerial: null,
      survey: null,
    });
  });

  it("reads every step's work", () => {
    const shown = parseProgress({
      frame: [1000, 2000, 1040, 2030],
      parcels: [RING],
      buildings: [RING, RING],
      terrain: {
        bbox: [1000, 2000, 1040, 2030],
        low_m: 102,
        high_m: 112.5,
        url: "/sites/s/progress/terrain.png",
      },
      aerial: {
        bbox: [1000, 2000, 1040, 2030],
        url: "/sites/s/progress/aerial.png",
      },
      survey: {
        concepts: ["building", "tree"],
        asking: "tree",
        found: [{ concept: "building", rings: [RING] }],
      },
    });
    expect(shown.frame).toEqual([1000, 2000, 1040, 2030]);
    expect(shown.parcels).toHaveLength(1);
    expect(shown.buildings).toHaveLength(2);
    expect(shown.terrain).toEqual({
      bbox: [1000, 2000, 1040, 2030],
      lowM: 102,
      highM: 112.5,
      url: "/api/sites/s/progress/terrain.png",
    });
    expect(shown.aerial?.url).toBe("/api/sites/s/progress/aerial.png");
    expect(shown.survey).toEqual({
      concepts: ["building", "tree"],
      asking: "tree",
      found: [{ concept: "building", rings: [RING] }],
    });
  });

  it("refuses a reply that isn't a build's progress", () => {
    expect(() => parseProgress({ ...EMPTY, frame: [1, 2] })).toThrow(ApiError);
    expect(() => parseProgress({ ...EMPTY, parcels: [[[1]]] })).toThrow(
      ApiError,
    );
  });
});

describe("the square frame", () => {
  it("is the frame's longer side, centred on it", () => {
    expect(squareFrame([1000, 2000, 1040, 2030])).toEqual({
      west: 1000,
      north: 2035,
      side: 40,
    });
  });

  it("places a bbox in it, north at the top", () => {
    const frame = squareFrame([1000, 2000, 1040, 2030]);
    expect(placed([1000, 2000, 1040, 2030], frame)).toEqual({
      x: 0,
      y: 5,
      width: 40,
      height: 30,
    });
  });

  it("draws a ring in it as a closed path", () => {
    const frame = squareFrame([1000, 2000, 1040, 2030]);
    expect(ringPath(RING as [number, number][], frame)).toBe(
      "M10 25L20 25L20 15L10 25Z",
    );
  });
});
