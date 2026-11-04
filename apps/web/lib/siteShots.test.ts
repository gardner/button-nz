import { describe, expect, it } from "vitest";

import type { Site } from "./api";
import { toNztm } from "./nztm";
import type { BuildProgress } from "./progress";
import type { Relief } from "./relief";
import { siteShots } from "./siteShots";
import { EMPTY_SITE_MAP, type SiteMap } from "./siteMap";

const AERIAL = {
  bbox: [1505986, 5336491, 1506062, 5336596] as [
    number,
    number,
    number,
    number,
  ],
  url: "/api/sites/s/aerial.png",
};
const PARCEL: [number, number][] = [
  [1506000, 5336500],
  [1506040, 5336500],
  [1506040, 5336570],
  [1506000, 5336500],
];
const SITE = {
  aerial: AERIAL,
  parcels: [{ id: 1, appellation: "Section 995", ring: PARCEL }],
} as unknown as Site;
const CORNER: [number, number] = [171.8628767, -42.1174514];
const SITE_MAP: SiteMap = {
  ...EMPTY_SITE_MAP,
  buildings: {
    type: "FeatureCollection",
    features: [
      {
        id: "b1",
        properties: { baseM: 1, heightM: 4 },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              CORNER,
              [171.8629711, -42.1174508],
              [171.8629717, -42.1175027],
              CORNER,
            ],
          ],
        },
      },
      {
        id: "b2",
        properties: { baseM: null, heightM: null },
        geometry: {
          type: "MultiPolygon",
          coordinates: [[[CORNER, CORNER, CORNER]], [[CORNER, CORNER, CORNER]]],
        },
      },
    ],
  },
};
const NOTHING = { site: null, siteMap: null, progress: null, relief: null };

function relief(...tiers: Relief["tiers"]): Relief {
  return { making: false, tiers };
}

describe("siteShots", () => {
  it("has nothing to show before the site's data has come", () => {
    expect(siteShots(NOTHING)).toEqual([]);
  });

  it("draws the site's aerial with its parcels and LINZ building outlines, in NZTM", () => {
    const [shot] = siteShots({ ...NOTHING, site: SITE, siteMap: SITE_MAP });
    expect(shot.kind).toBe("aerial");
    if (shot.kind !== "aerial") return;
    expect(shot.picture.frame).toEqual(AERIAL.bbox);
    expect(shot.picture.aerial).toEqual(AERIAL);
    expect(shot.picture.parcels).toEqual([PARCEL]);
    expect(shot.picture.buildings).toHaveLength(3); // a polygon, a multipolygon's two
    expect(shot.picture.buildings[0][0]).toEqual(toNztm(CORNER));
  });

  it("shows the build's own picture (its SAM finds too), and its terrain preview, when the build recorded them", () => {
    const progress: BuildProgress = {
      frame: AERIAL.bbox,
      parcels: [PARCEL],
      buildings: [],
      terrain: { bbox: AERIAL.bbox, url: "/api/t.png", lowM: 186, highM: 197 },
      aerial: AERIAL,
      survey: { concepts: ["tree"], asking: null, found: [] },
    };
    const shots = siteShots({
      ...NOTHING,
      site: SITE,
      siteMap: SITE_MAP,
      progress,
    });
    expect(shots).toEqual([
      { kind: "aerial", picture: progress },
      { kind: "terrain", src: "/api/t.png", lowM: 186, highM: 197 },
    ]);
  });

  it("shows the fly-over when it is ready, else the depth map, and nothing still being made", () => {
    const depth = {
      tier: "depth",
      status: "ready" as const,
      files: { preview: "/api/d.png", depth16: "/api/d16.png" },
      error: null,
    };
    const flyover = {
      tier: "flyover",
      status: "ready" as const,
      files: { video: "/api/f.mp4", still: "/api/f.png" },
      error: null,
    };
    expect(siteShots({ ...NOTHING, relief: relief(depth, flyover) })).toEqual([
      { kind: "flyover", video: "/api/f.mp4", still: "/api/f.png" },
    ]);
    expect(siteShots({ ...NOTHING, relief: relief(depth) })).toEqual([
      { kind: "depth", src: "/api/d.png" },
    ]);
    const pending = { ...depth, status: "running" as const, files: {} };
    expect(siteShots({ ...NOTHING, relief: relief(pending) })).toEqual([]);
  });
});
