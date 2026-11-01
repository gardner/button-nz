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
import {
  type Fields,
  list,
  number,
  oneOf,
  optional,
  record,
  text,
} from "./fields";
import { type FeatureCollection, parseCollection } from "./geo";
import { request } from "./http";

export interface SurveyedFeature {
  id: string;
  concept: string;
  status: FeatureStatus;
  decision: Decision | null; // null until a person decides
  heightM: number | null; // its top above the site's datum, where the LiDAR covers it
  baseM: number | null; // its bottom, the same way
}

/** A thing that can be stood up on the map: its bottom (`baseM`) and top
 * (`heightM`), in metres above the site's datum (#86 v1.1, #95); null beyond
 * the LiDAR, or where they weren't measured. */
export interface Raised {
  baseM: number | null;
  heightM: number | null;
}

export interface SiteMap {
  parcels: FeatureCollection<null>;
  buildings: FeatureCollection<Raised>; // LINZ outlines, as tall as the LiDAR says
  canopy: FeatureCollection<Raised>; // trees: the LiDAR over 2 m, outside the buildings
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

/** A check whose line the map can't draw, and why (never left out silently). */
export interface Undrawn {
  check: string;
  reason: string;
}

export interface DesignMap {
  outline: FeatureCollection<Raised>; // all it covers from above, eaves too
  walls: FeatureCollection<Raised>; // from its floor to its roof
  distances: FeatureCollection<Distance>;
  unknown: Undrawn[];
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
    canopy: parseCollection(map.canopy, "canopy", raised),
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
          ...raised(f.properties),
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
    unknown: list(map, "unknown").map((raw) => {
      const u = record(raw, "unknown check");
      return { check: text(u, "check"), reason: text(u, "reason") };
    }),
  };
}

/** Bottom and top; absent or null where not measured. */
export function raised(p: Fields): Raised {
  return {
    heightM: p.height_m === undefined ? null : optional(p, "height_m", number),
    baseM: p.base_m === undefined ? null : optional(p, "base_m", number),
  };
}

/** The features that can be stood up: those with every height measured. */
export function measured<P extends Raised>(
  data: FeatureCollection<P>,
): FeatureCollection<P> {
  return {
    ...data,
    features: data.features.filter(
      (f) => f.properties.baseM !== null && f.properties.heightM !== null,
    ),
  };
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
