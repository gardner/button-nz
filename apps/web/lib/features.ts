/**
 * The survey of what stands on and around the site (`button_nz.api.features`):
 * an NZTM GeoJSON FeatureCollection, each feature found on the aerial, checked
 * against the LiDAR, and decided by a person.
 */

import type { Point } from "./api";
import {
  ApiError,
  type Fields,
  asList,
  asPoint,
  flag,
  list,
  number,
  oneOf,
  optional,
  record,
  text,
} from "./fields";

export type FeatureStatus =
  | "agrees" // the label and the LiDAR concur
  | "conflict" // they don't: a person decides
  | "transient" // e.g. a parked car: not part of the site
  | "unchecked" // no rule for the concept, or too small for 1 m LiDAR
  | "unlabelled"; // raised ground no label covers

export type Decision = "building" | "keep_clear" | "ignore";

export type Polygon = Point[][]; // the outer ring, then any holes

export interface SiteFeature {
  id: string;
  concept: string;
  score: number | null; // the segmentation's confidence; none when unlabelled
  areaM2: number;
  maxHeightM: number | null; // none when too small for the LiDAR
  status: FeatureStatus;
  note: string;
  decision: Decision | null;
  suggested: boolean; // the survey's suggestion, not yet the owner's own
  polygons: Polygon[];
}

export interface Survey {
  id: string;
  buildingsComplete: boolean; // the owner says every building is listed
  decidedBy: string | null; // the server fixed the survey as this person decided it
  features: SiteFeature[];
}

export const STATUSES: readonly FeatureStatus[] = [
  "agrees",
  "conflict",
  "transient",
  "unchecked",
  "unlabelled",
];
export const DECISIONS: readonly Decision[] = [
  "building",
  "keep_clear",
  "ignore",
];

export function parseSurvey(raw: unknown): Survey {
  const survey = record(raw, "survey");
  if (survey.crs !== "EPSG:2193") {
    // The plan draws coordinates as NZTM metres: anything else would be distorted.
    throw new ApiError(
      `expected the survey in EPSG:2193, not ${JSON.stringify(survey.crs)}`,
    );
  }
  return {
    id: text(survey, "survey_id"),
    buildingsComplete: flag(survey, "buildings_complete"),
    decidedBy: flag(survey, "fixed") ? text(survey, "decided_by") : null,
    features: list(survey, "features").map(parseFeature),
  };
}

export function parseFeature(raw: unknown): SiteFeature {
  const feature = record(raw, "feature");
  const properties = record(feature.properties, "properties");
  return {
    id: text(feature, "id"),
    concept: text(properties, "concept"),
    score: optional(properties, "score", number),
    areaM2: number(properties, "area_m2"),
    maxHeightM: optional(properties, "max_height_m", number),
    status: oneOf(properties, "status", STATUSES),
    note: text(properties, "note"),
    decision: optional(properties, "decision", (f, k) =>
      oneOf(f, k, DECISIONS),
    ),
    suggested: flag(properties, "suggested"),
    polygons: parsePolygons(record(feature.geometry, "geometry")),
  };
}

function parsePolygons(geometry: Fields): Polygon[] {
  const type = oneOf(geometry, "type", ["Polygon", "MultiPolygon"]);
  const coordinates = list(geometry, "coordinates");
  return type === "Polygon"
    ? [asPolygon(coordinates)]
    : coordinates.map(asPolygon);
}

function asPolygon(value: unknown): Polygon {
  return asList(value, "polygon").map((ring) =>
    asList(ring, "ring").map(asPoint),
  );
}
