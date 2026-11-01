import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./fields";
import { DESIGN_MAP, SITE_MAP } from "./fixtures-sites";
import { getDesignMap, getSiteMap, parseSiteMap } from "./siteMap";

function serve(body: unknown): ReturnType<typeof vi.fn> {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(body)));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("getSiteMap", () => {
  it("reads every layer, and each surveyed feature's decision", async () => {
    const fetch = serve(SITE_MAP);
    const map = await getSiteMap("35-victory-street-reefton");
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/sites/35-victory-street-reefton/map",
    );
    expect(map.features.features.map((f) => f.properties)).toEqual([
      {
        id: "1",
        concept: "shed",
        status: "agrees",
        decision: "ignore",
        heightM: null,
        baseM: null,
      },
      {
        id: "3",
        concept: "tree",
        status: "agrees",
        decision: "keep_clear",
        heightM: 7.2,
        baseM: null, // absent: not measured
      },
    ]);
    expect(map.buildings.features.map((f) => f.properties)).toEqual([
      { heightM: 6.2, baseM: 2.2 },
      { heightM: null, baseM: null }, // the LiDAR has no cell inside it
    ]);
    expect(map.canopy.features[0].properties).toEqual({
      baseM: 1.2,
      heightM: 9.3,
    });
    expect(map.room.features).toHaveLength(1);
    expect(map.halos.features).toHaveLength(0);
  });

  it("reads an undecided feature", () => {
    const undecided = {
      ...SITE_MAP,
      features: {
        ...SITE_MAP.features,
        features: [
          {
            ...SITE_MAP.features.features[0],
            properties: {
              id: "1",
              concept: "shed",
              status: "conflict",
              decision: null,
              height_m: null,
            },
          },
        ],
      },
    };
    expect(parseSiteMap(undecided).features.features[0].properties).toEqual({
      id: "1",
      concept: "shed",
      status: "conflict",
      decision: null,
      heightM: null,
      baseM: null,
    });
  });

  it.each([
    [{ ...SITE_MAP, room: undefined }],
    [{ ...SITE_MAP, canopy: undefined }],
    [
      {
        ...SITE_MAP,
        buildings: {
          ...SITE_MAP.buildings,
          features: [
            {
              ...SITE_MAP.buildings.features[0],
              properties: { id: 25, height_m: "tall", base_m: 0 },
            },
          ],
        },
      },
    ],
    [
      {
        ...SITE_MAP,
        features: {
          ...SITE_MAP.features,
          features: [
            {
              ...SITE_MAP.features.features[0],
              properties: {
                id: "1",
                concept: "shed",
                status: "agrees",
                decision: "demolish",
              },
            },
          ],
        },
      },
    ],
  ])("refuses a map it can't draw", (raw) => {
    expect(() => parseSiteMap(raw)).toThrow(ApiError);
  });
});

describe("getDesignMap", () => {
  it("reads a design whose heights weren't measured", async () => {
    const unmeasured = {
      ...DESIGN_MAP,
      walls: {
        ...DESIGN_MAP.walls,
        features: [{ ...DESIGN_MAP.walls.features[0], properties: {} }],
      },
    };
    serve(unmeasured);
    const map = await getDesignMap("abc123");
    expect(map.walls.features[0].properties).toEqual({
      baseM: null,
      heightM: null,
    });
  });

  it("reads the checks it couldn't draw, and why, and refuses a map without them", async () => {
    serve({
      ...DESIGN_MAP,
      unknown: [
        {
          check: "building_separation",
          reason: "the survey has changed since the design was checked",
        },
      ],
    });
    expect((await getDesignMap("abc123")).unknown).toEqual([
      {
        check: "building_separation",
        reason: "the survey has changed since the design was checked",
      },
    ]);
    serve({ ...DESIGN_MAP, unknown: undefined });
    await expect(getDesignMap("abc123")).rejects.toThrow(ApiError);
  });

  it("reads the outline, the walls and each distance with its rule", async () => {
    const fetch = serve(DESIGN_MAP);
    const map = await getDesignMap("abc123");
    expect(fetch.mock.calls[0][0]).toBe("/api/designs/abc123/map");
    expect(map.walls.features[0].properties).toEqual({
      baseM: 0.3,
      heightM: 3.9,
    });
    expect(map.outline.features[0].properties).toEqual({
      baseM: 0.3,
      heightM: 3.9,
    });
    expect(map.distances.features[0].properties).toEqual({
      check: "title_boundary_setback",
      metres: 3.2,
      required: 2,
    });
  });
});
