/**
 * The layers that show the rules on the land (#86): a site's parcels,
 * buildings, surveyed features and the room the exemption leaves, and an
 * accepted design's outline, walls and distances, all in EPSG:4326. The
 * server draws them from the geometry the evaluator checks; the browser only
 * shows them.
 */

import {
  DECISIONS,
  type Decision,
  type FeatureStatus,
  STATUSES,
} from "./features";
import { type Fields, number, oneOf, optional, text } from "./fields";
import { type FeatureCollection, parseCollection } from "./geo";
import { API, request } from "./http";

export interface SurveyedFeature {
  id: string;
  concept: string;
  status: FeatureStatus;
  decision: Decision | null; // null until a person decides
  heightM: number | null; // its LiDAR height above the ground, where it has one
}

/** How tall a thing stands, in metres above the ground under it (#86 v1.1);
 * null where the LiDAR has no cell inside it. */
export interface Tall {
  heightM: number | null;
}

/** A thing that can be stood up on the map: from `baseM` to `heightM`
 * (null where they weren't measured). */
export interface Raised extends Tall {
  baseM: number | null;
}

export interface SiteMap {
  parcels: FeatureCollection<null>;
  buildings: FeatureCollection<Raised>; // LINZ outlines, as tall as the LiDAR says
  canopy: FeatureCollection<Tall>; // trees: the LiDAR over 2 m, outside the buildings
  features: FeatureCollection<SurveyedFeature>;
  setback: FeatureCollection<null>; // the 2 m band inside the title boundary
  halos: FeatureCollection<null>; // 2 m around confirmed buildings
  keep_clear: FeatureCollection<null>;
  room: FeatureCollection<null>; // where a dwelling may stand
}

export interface Distance {
  check: string;
  metres: number;
  required: number;
}

export interface DesignMap {
  outline: FeatureCollection<Raised>; // all it covers from above, eaves too
  walls: FeatureCollection<Raised>; // from its floor to its roof
  distances: FeatureCollection<Distance>;
}

const PLAIN = ["parcels", "setback", "halos", "keep_clear", "room"] as const;

export async function getSiteMap(siteId: string): Promise<SiteMap> {
  return parseSiteMap(
    await request(`/sites/${encodeURIComponent(siteId)}/map`),
  );
}

export function parseSiteMap(raw: unknown): SiteMap {
  const map = (raw ?? {}) as Fields;
  const plain = Object.fromEntries(
    PLAIN.map((key) => [key, parseCollection(map[key], key, () => null)]),
  ) as Record<(typeof PLAIN)[number], FeatureCollection<null>>;
  const features = parseCollection(map.features, "features", (p) => p);
  return {
    ...plain,
    buildings: parseCollection(map.buildings, "buildings", raised),
    canopy: parseCollection(map.canopy, "canopy", tall),
    features: {
      type: "FeatureCollection",
      features: features.features.map((f) => ({
        ...f,
        properties: {
          id: text(f.properties, "id"), // #88 writes it in the properties
          concept: text(f.properties, "concept"),
          status: oneOf(f.properties, "status", STATUSES),
          decision: optional(f.properties, "decision", (p, k) =>
            oneOf(p, k, DECISIONS),
          ),
          heightM: optional(f.properties, "height_m", number),
        },
      })),
    },
  };
}

export async function getDesignMap(jobId: string): Promise<DesignMap> {
  const map = (await request(
    `/designs/${encodeURIComponent(jobId)}/map`,
  )) as Fields;
  return {
    outline: parseCollection(map.outline, "outline", raised),
    walls: parseCollection(map.walls, "walls", raised),
    distances: parseCollection(map.distances, "distances", (p) => ({
      check: text(p, "check"),
      metres: number(p, "metres"),
      required: number(p, "required"),
    })),
  };
}

export function tall(p: Fields): Tall {
  return { heightM: optional(p, "height_m", number) };
}

/** Floor and roof, or base and top; absent or null where not measured. */
function raised(p: Fields): Raised {
  return {
    heightM: p.height_m === undefined ? null : optional(p, "height_m", number),
    baseM: p.base_m === undefined ? null : optional(p, "base_m", number),
  };
}

/** The features that can be stood up: those with every height measured. */
export function measured<P extends Tall>(
  data: FeatureCollection<P>,
): FeatureCollection<P> {
  return {
    ...data,
    features: data.features.filter(
      (f) =>
        f.properties.heightM !== null &&
        (!("baseM" in f.properties) ||
          (f.properties as Partial<Raised>).baseM !== null),
    ),
  };
}

/** Terrain-RGB tiles of a site's bare earth (DEM), metres above its
 * ground: 404 outside its bounds, where the map is flat (#86 v1.1). The
 * buildings and trees stand on it as extrusions, crisper than a draped DSM. */
export function terrainTiles(siteId: string): string {
  return `${API}/sites/${encodeURIComponent(siteId)}/terrain/{z}/{x}/{y}.png`;
}

const NONE = { type: "FeatureCollection" as const, features: [] };

/** A site map with nothing in it, to draw while the real one is on its way:
 * its layers keep their place under the design's. */
export const EMPTY_SITE_MAP: SiteMap = {
  parcels: NONE,
  buildings: NONE,
  canopy: NONE,
  features: NONE,
  setback: NONE,
  halos: NONE,
  keep_clear: NONE,
  room: NONE,
};
