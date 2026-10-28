import { describe, expect, it } from "vitest";

import type { Point } from "./api";
import { interiorPoint, planView } from "./plan";

const SQUARE: [number, number][] = [
  [1000, 2000],
  [1010, 2000],
  [1010, 2020],
  [1000, 2020],
  [1000, 2000],
];

describe("planView", () => {
  it("draws NZTM metres at true scale with north up", () => {
    const view = planView([SQUARE], [1000, 2000, 1010, 2020], 2);
    // A 2 m margin on every side: 14 m x 24 m.
    expect(view.viewBox).toBe("0 0 14 24");
    // South-west corner (1000, 2000) is bottom-left; north-east (1010, 2020) top-right.
    expect(view.paths[0]).toBe("M2,22 L12,22 L12,2 L2,2 L2,22 Z");
  });

  it("chooses a round scale bar no wider than a third of the plan", () => {
    expect(planView([SQUARE], [1000, 2000, 1040, 2020], 0).scaleBarM).toBe(10);
    expect(planView([SQUARE], [1000, 2000, 1010, 2020], 0).scaleBarM).toBe(2);
  });

  it("places a point, such as the address, in the same frame", () => {
    const view = planView([SQUARE], [1000, 2000, 1010, 2020], 2);
    expect(view.point([1005, 2010])).toEqual([7, 12]);
  });

  it("outlines a polygon with a hole as one path", () => {
    const view = planView([SQUARE], [1000, 2000, 1010, 2020], 2);
    const hole: [number, number][] = [
      [1004, 2004],
      [1006, 2004],
      [1006, 2006],
      [1004, 2004],
    ];
    expect(view.outline([SQUARE, hole])).toBe(
      "M2,22 L12,22 L12,2 L2,2 L2,22 Z M6,18 L8,18 L8,16 L6,18 Z",
    );
  });
});

describe("interiorPoint", () => {
  const inside = (rings: Point[][], [x, y]: Point): boolean => {
    let crossings = 0; // even-odd: holes are outside
    for (const ring of rings) {
      for (let i = 0; i + 1 < ring.length; i++) {
        const [[x1, y1], [x2, y2]] = [ring[i], ring[i + 1]];
        if (y1 > y !== y2 > y && x < x1 + ((y - y1) * (x2 - x1)) / (y2 - y1))
          crossings++;
      }
    }
    return crossings % 2 === 1;
  };

  it("lands inside a U shape whose middle is outside", () => {
    const u: Point[] = [
      [0, 0],
      [10, 0],
      [10, 10],
      [7, 10],
      [7, 3],
      [3, 3],
      [3, 10],
      [0, 10],
      [0, 0],
    ];
    expect(inside([u], [5, 5])).toBe(false); // the bounding box's centre
    expect(inside([u], interiorPoint([u]))).toBe(true);
  });

  it("lands outside a hole in the middle", () => {
    const outer: Point[] = [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [0, 0],
    ];
    const hole: Point[] = [
      [2, 2],
      [8, 2],
      [8, 8],
      [2, 8],
      [2, 2],
    ];
    expect(inside([outer, hole], interiorPoint([outer, hole]))).toBe(true);
  });
});
