/**
 * The button-nz API (Python, `button_nz.api`), reached through the
 * same-origin proxy at /api (see next.config.ts). Responses are checked as
 * they arrive: a shape this app doesn't expect is an ApiError, not a guess.
 */

import {
  ApiError,
  asList,
  asPoint,
  asText,
  flag,
  isRecord,
  list,
  number,
  numbers,
  oneOf,
  optional,
  record,
  text,
} from "./fields";
import {
  type Decision,
  type SiteFeature,
  type Survey,
  parseFeature,
  parseSurvey,
} from "./features";

export { ApiError };

export const API = "/api";

export type JobStatus = "queued" | "running" | "done" | "failed";
export type Verdict = "pass" | "fail" | "unknown" | "error";

export interface Attempt {
  number: number;
  status: Verdict;
  feedback: string;
  observations: string[];
  files: Record<string, string>; // artifact name -> URL through the proxy
}

export interface Job {
  id: string;
  brief: string;
  allowObservations: boolean;
  status: JobStatus;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  acceptedAttempt: number | null;
  parentId: string | null; // the design this one revises, if it is a revision
  instruction: string | null; // the owner's change to that design
  attempts: Attempt[];
  illustrating: boolean; // done, and its AI visual is still being made
}

export type Point = [number, number]; // NZTM (EPSG:2193) metres

export interface Parcel {
  id: number;
  appellation: string;
  ring: Point[];
}

export interface Source {
  key: string;
  title: string;
  licence: string;
  attribution: string;
  capture: { start: string; end: string } | null;
}

export interface Site {
  name: string;
  title: string;
  valuationNumber: string;
  address: Point;
  extent: [number, number, number, number]; // west, south, east, north
  parcels: Parcel[];
  sources: Source[];
  openItems: string[];
  aerial: Aerial | null; // a photo to draw under the plan, if the API has one
}

export interface Aerial {
  bbox: [number, number, number, number]; // NZTM west, south, east, north
  url: string; // through the proxy
}

const JOB_STATUSES: readonly JobStatus[] = [
  "queued",
  "running",
  "done",
  "failed",
];
const VERDICTS: readonly Verdict[] = ["pass", "fail", "unknown", "error"];

export async function getSite(): Promise<Site> {
  return parseSite(await request("/site"));
}

export async function createDesign(
  brief: string,
  allowObservations: boolean,
): Promise<Job> {
  return parseJob(
    await send("POST", "/designs", {
      brief,
      allow_observations: allowObservations,
    }),
  );
}

/** Ask for a change to design `id`, in the owner's words. The new job keeps
 * its brief and starts from its accepted attempt; refused (409) if it has none. */
export async function reviseDesign(
  id: string,
  instruction: string,
  allowObservations: boolean,
): Promise<Job> {
  return parseJob(
    await send("POST", `/designs/${encodeURIComponent(id)}/revisions`, {
      instruction,
      allow_observations: allowObservations,
    }),
  );
}

export async function getDesign(id: string): Promise<Job> {
  return parseJob(await request(`/designs/${encodeURIComponent(id)}`));
}

export async function getFeatures(): Promise<Survey> {
  return parseSurvey(await request("/site/features"));
}

/** Record a decision about feature `id` of survey `surveyId`. Refused (409)
 * if a newer survey has been written since: its ids may mean other things. */
export async function decideFeature(
  surveyId: string,
  id: string,
  decision: Decision,
): Promise<SiteFeature> {
  return parseFeature(
    await send("PUT", `/site/features/${encodeURIComponent(id)}`, {
      decision,
      survey_id: surveyId,
    }),
  );
}

/** Say every building on the site is listed (or not). Refused (409) while
 * anything that might be a building is undecided, or if the survey changed. */
export async function setBuildingsComplete(
  surveyId: string,
  complete: boolean,
): Promise<boolean> {
  const survey = record(
    await send("PUT", "/site/survey", {
      buildings_complete: complete,
      survey_id: surveyId,
    }),
    "survey",
  );
  return flag(survey, "buildings_complete");
}

function send(
  method: "POST" | "PUT",
  path: string,
  body: object,
): Promise<unknown> {
  return request(path, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${API}${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      reason(body) ?? `${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return body;
}

function reason(body: unknown): string | null {
  if (!isRecord(body) || body.detail === undefined) return null;
  return typeof body.detail === "string"
    ? body.detail
    : JSON.stringify(body.detail);
}

export function parseJob(raw: unknown): Job {
  const job = record(raw, "job");
  return {
    id: text(job, "id"),
    brief: text(job, "brief"),
    allowObservations: flag(job, "allow_observations"),
    status: oneOf(job, "status", JOB_STATUSES),
    createdAt: text(job, "created_at"),
    startedAt: optional(job, "started_at", text),
    finishedAt: optional(job, "finished_at", text),
    error: optional(job, "error", text),
    acceptedAttempt: optional(job, "accepted_attempt", number),
    parentId: optional(job, "parent_id", text),
    instruction: optional(job, "instruction", text),
    attempts: list(job, "attempts").map(parseAttempt),
    illustrating: flag(job, "illustrating"),
  };
}

function parseAttempt(raw: unknown): Attempt {
  const attempt = record(raw, "attempt");
  const files = record(attempt.files, "files");
  return {
    number: number(attempt, "number"),
    status: oneOf(attempt, "status", VERDICTS),
    feedback: text(attempt, "feedback"),
    observations: list(attempt, "observations").map((o) =>
      asText(o, "observation"),
    ),
    files: Object.fromEntries(
      Object.keys(files).map((name) => [name, `${API}${text(files, name)}`]),
    ),
  };
}

export function parseSite(raw: unknown): Site {
  const site = record(raw, "site");
  if (site.crs !== "EPSG:2193") {
    // The plan draws coordinates as NZTM metres: anything else would be distorted.
    throw new ApiError(
      `expected the site in EPSG:2193, not ${JSON.stringify(site.crs)}`,
    );
  }
  const parcels = record(site.parcels, "parcels");
  const sources = record(site.sources, "sources");
  return {
    name: text(site, "name"),
    title: text(site, "title"),
    valuationNumber: text(site, "valuation_number"),
    address: asPoint(site.address),
    extent: numbers(site.extent, 4) as Site["extent"],
    parcels: list(parcels, "features").map(parseParcel),
    sources: Object.keys(sources).map((key) => parseSource(key, sources[key])),
    openItems: list(site, "open_items").map((item) =>
      asText(item, "open item"),
    ),
    aerial: site.aerial === null ? null : parseAerial(site.aerial),
  };
}

function parseAerial(raw: unknown): Aerial {
  const aerial = record(raw, "aerial");
  return {
    bbox: numbers(aerial.bbox, 4) as Aerial["bbox"],
    url: `${API}${text(aerial, "url")}`,
  };
}

function parseParcel(raw: unknown): Parcel {
  const feature = record(raw, "parcel");
  const geometry = record(feature.geometry, "geometry");
  const [exterior] = list(geometry, "coordinates");
  return {
    id: number(feature, "id"),
    appellation: text(record(feature.properties, "properties"), "appellation"),
    ring: asList(exterior, "ring").map(asPoint),
  };
}

function parseSource(key: string, raw: unknown): Source {
  const source = record(raw, key);
  const capture =
    source.capture === null ? null : record(source.capture, "capture");
  return {
    key,
    title: text(source, "title"),
    licence: text(source, "licence"),
    attribution: text(source, "attribution"),
    capture: capture && {
      start: text(capture, "start"),
      end: text(capture, "end"),
    },
  };
}
