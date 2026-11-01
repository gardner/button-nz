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
      { id: "1", concept: "shed", status: "agrees", decision: "ignore" },
      { id: "3", concept: "tree", status: "agrees", decision: "keep_clear" },
    ]);
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
    });
  });

  it.each([
    [{ ...SITE_MAP, room: undefined }],
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
  it("reads the outline, the walls and each distance with its rule", async () => {
    const fetch = serve(DESIGN_MAP);
    const map = await getDesignMap("abc123");
    expect(fetch.mock.calls[0][0]).toBe("/api/designs/abc123/map");
    expect(map.walls.features).toHaveLength(1);
    expect(map.distances.features[0].properties).toEqual({
      check: "title_boundary_setback",
      metres: 3.2,
      required: 2,
    });
  });
});
