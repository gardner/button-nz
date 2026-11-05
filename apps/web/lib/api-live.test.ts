import { describe, expect, it } from "vitest";

import { ApiError, parseJob } from "./api";
import { JOB } from "./fixtures";
import { LIVE } from "./fixtures-sites";

function running(live: unknown) {
  return parseJob({ ...JOB, status: "running", accepted_attempt: null, live });
}

describe("a running job's live state", () => {
  it("reads when its step began and its newest view was made, on this browser's clock, and where a home fits", () => {
    // The API says how long ago (its clock needn't agree with this one's).
    const now = Date.parse("2026-11-05T00:16:17Z");
    const live = parseJob(
      { ...JOB, status: "running", accepted_attempt: null, live: LIVE },
      now,
    ).live!;
    expect(live.since).toBe("2026-11-05T00:12:34.500Z"); // 222.5 s before
    expect(live.newestViewAt).toBe("2026-11-05T00:15:17.000Z"); // 60 s before
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
    const { step_s, newest_view_s, placement, ...before } = LIVE;
    void [step_s, newest_view_s, placement];
    const live = running(before).live!;
    expect(live.since).toBeNull();
    expect(live.newestViewAt).toBeNull();
    expect(live.placement).toBeNull();
  });

  it("reads a run with no views yet, and none whose plan places", () => {
    const live = running({
      ...LIVE,
      observations: [],
      newest_view_s: null,
      placement: null,
    }).live!;
    expect(live.newestViewAt).toBeNull();
    expect(live.placement).toBeNull();
  });

  it("refuses an age that isn't a number", () => {
    expect(() => running({ ...LIVE, step_s: "3:42" })).toThrow(ApiError);
    expect(() => running({ ...LIVE, newest_view_s: "1m" })).toThrow(ApiError);
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
