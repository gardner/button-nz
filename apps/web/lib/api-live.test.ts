import { describe, expect, it } from "vitest";

import { ApiError, parseJob } from "./api";
import { JOB } from "./fixtures";
import { LIVE } from "./fixtures-sites";

function running(live: unknown) {
  return parseJob({ ...JOB, status: "running", accepted_attempt: null, live });
}

describe("a running job's live state", () => {
  it("reads when its step began, when its newest view was made, and where a home fits", () => {
    const live = running(LIVE).live!;
    expect(live.since).toBe("2026-11-05T00:12:35.200000Z");
    expect(live.newestViewAt).toBe("2026-11-05T00:12:35.100000Z");
    expect(live.observations).toEqual([
      "/api/designs/abc123/attempts/1/observation-4.png",
    ]);
    expect(live.placement).toEqual({
      plan: { lengthM: 10, widthM: 4.8, eavesM: 0.6 },
      walls: LIVE.placement.walls,
      outline: LIVE.placement.outline,
      clearances: {
        titleBoundaryM: 2.413,
        sectionLineM: 2.187,
        buildingM: null, // the site lists none
        streetEdgeM: 6.76,
      },
      floorRangeM: [189.633, 190.47],
      foundInS: 1.6,
    });
  });

  it("reads an API from before #188 as having none of them", () => {
    const { since, newest_view_at, placement, ...before } = LIVE;
    void [since, newest_view_at, placement];
    const live = running(before).live!;
    expect(live.since).toBeNull();
    expect(live.newestViewAt).toBeNull();
    expect(live.placement).toBeNull();
  });

  it("reads a run with no views yet, and none whose plan places", () => {
    const live = running({
      ...LIVE,
      observations: [],
      newest_view_at: null,
      placement: null,
    }).live!;
    expect(live.newestViewAt).toBeNull();
    expect(live.placement).toBeNull();
  });

  it.each([
    ["an open ring", { walls: LIVE.placement.walls.slice(0, 4) }],
    [
      "a ring of too few corners",
      {
        walls: [
          [1, 2],
          [3, 4],
          [1, 2],
        ],
      },
    ],
    ["a position that isn't a pair", { outline: [[1], [2], [3], [1]] }],
    [
      "a clearance that isn't a number",
      { clearances: { title_boundary_m: "2" } },
    ],
    ["no clearance to the title boundary", { clearances: {} }],
    ["a floor range of one level", { floor_range_m: [189.6] }],
    ["no plan", { plan: null }],
    ["a time that isn't a number", { found_in_s: "soon" }],
  ])("refuses a placement with %s", (_, wrong) => {
    expect(() =>
      running({ ...LIVE, placement: { ...LIVE.placement, ...wrong } }),
    ).toThrow(ApiError);
  });
});
