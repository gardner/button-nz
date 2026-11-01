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
import { request } from "./http";

export interface SurveyedFeature {
  id: string;
  concept: string;
  status: FeatureStatus;
  decision: Decision | null; // null until a person decides
}

export interface SiteMap {
  parcels: FeatureCollection<null>;
  buildings: FeatureCollection<null>; // LINZ outlines
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
  outline: FeatureCollection<null>; // all it covers from above, eaves too
  walls: FeatureCollection<null>;
  distances: FeatureCollection<Distance>;
}

const PLAIN = [
  "parcels",
  "buildings",
  "setback",
  "halos",
  "keep_clear",
  "room",
] as const;

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
    features: {
      type: "FeatureCollection",
      features: features.features.map((f) => ({
        ...f,
        properties: {
          id: String(f.id),
          concept: text(f.properties, "concept"),
          status: oneOf(f.properties, "status", STATUSES),
          decision: optional(f.properties, "decision", (p, k) =>
            oneOf(p, k, DECISIONS),
          ),
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
    outline: parseCollection(map.outline, "outline", () => null),
    walls: parseCollection(map.walls, "walls", () => null),
    distances: parseCollection(map.distances, "distances", (p) => ({
      check: text(p, "check"),
      metres: number(p, "metres"),
      required: number(p, "required"),
    })),
  };
}
