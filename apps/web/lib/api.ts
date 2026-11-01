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
import { API, request, send } from "./http";
import { type Products, parseProducts } from "./products";

export { ApiError };

export { API };

export type JobStatus = "queued" | "running" | "done" | "failed";
export type Verdict = "pass" | "fail" | "unknown" | "error";

/** One of the evaluator's checks of an attempt, as it measured it. */
export interface Check {
  name: string;
  status: "pass" | "fail" | "unknown";
  detail: string;
  measured: Record<string, number>;
  rule: string; // where the limit comes from
}

export interface Attempt {
  number: number;
  status: Verdict;
  checks: Check[] | null; // null when the API can't tell, or doesn't send them
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
  siteId: string | null; // the site it is designed on; null on the demo site's API
  product: PlacedProduct | null; // the catalogue product it places, if any
  attempts: Attempt[];
  illustrating: boolean; // done, and its AI visual is still being made
  live: Live | null; // while it runs: what it is doing now
}

export type Phase = "thinking" | "observing" | "rendering" | "checking";
const PHASES: readonly Phase[] = [
  "thinking",
  "observing",
  "rendering",
  "checking",
];

/** A running design's current step, and the LiDAR views made so far in it. */
export interface Live {
  attempt: number;
  phase: Phase;
  detail: string; // the view asked for, when observing
  observations: string[]; // URLs through the proxy
}

/** A catalogue product a design places, as it was when placed: its walls are
 * its outside footprint. */
export interface PlacedProduct {
  id: string;
  name: string;
  lengthM: number;
  widthM: number;
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
  valuationNumber: string | null; // null where the council has none
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

/** Queue a design for `brief`; with `productId`, it places that product. */
export async function createDesign(
  brief: string,
  allowObservations: boolean,
  productId?: string,
  siteId?: string,
): Promise<Job> {
  const placing = productId === undefined ? {} : { product_id: productId };
  const site = siteId === undefined ? {} : { site_id: siteId };
  return parseJob(
    await send("POST", "/designs", {
      brief,
      allow_observations: allowObservations,
      ...placing,
      ...site,
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

/** The real prefab homes that fit inside design `id`'s accepted walls;
 * refused (409) if it has none. */
export async function getProducts(id: string): Promise<Products> {
  return parseProducts(
    await request(`/designs/${encodeURIComponent(id)}/products`),
  );
}

/** Where a site's survey is: the demo site's, or `siteId`'s. */
function surveyed(siteId: string | undefined): string {
  return siteId === undefined
    ? "/site"
    : `/sites/${encodeURIComponent(siteId)}`;
}

export async function getFeatures(siteId?: string): Promise<Survey> {
  return parseSurvey(await request(`${surveyed(siteId)}/features`));
}

/** Record a decision about feature `id` of survey `surveyId`. Refused (409)
 * if a newer survey has been written since: its ids may mean other things. */
export async function decideFeature(
  surveyId: string,
  id: string,
  decision: Decision,
  siteId?: string,
): Promise<SiteFeature> {
  return parseFeature(
    await send(
      "PUT",
      `${surveyed(siteId)}/features/${encodeURIComponent(id)}`,
      {
        decision,
        survey_id: surveyId,
      },
    ),
  );
}

/** Say every building on the site is listed (or not). Refused (409) while
 * anything that might be a building is undecided, or if the survey changed. */
export async function setBuildingsComplete(
  surveyId: string,
  complete: boolean,
  siteId?: string,
): Promise<boolean> {
  const survey = record(
    await send("PUT", `${surveyed(siteId)}/survey`, {
      buildings_complete: complete,
      survey_id: surveyId,
    }),
    "survey",
  );
  return flag(survey, "buildings_complete");
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
    siteId: "site_id" in job ? optional(job, "site_id", text) : null,
    product: optional(job, "product", (f, k) => parsePlaced(f[k])),
    attempts: list(job, "attempts").map(parseAttempt),
    illustrating: flag(job, "illustrating"),
    live: optional(job, "live", (f, k) => parseLive(f[k])),
  };
}

function parseLive(raw: unknown): Live {
  const live = record(raw, "live");
  return {
    attempt: number(live, "attempt"),
    phase: oneOf(live, "phase", PHASES),
    detail: text(live, "detail"),
    observations: list(live, "observations").map(
      (url) => `${API}${asText(url, "observation")}`,
    ),
  };
}

function parsePlaced(raw: unknown): PlacedProduct {
  const product = record(raw, "product");
  return {
    id: text(product, "id"),
    name: text(product, "name"),
    lengthM: number(product, "length_m"),
    widthM: number(product, "width_m"),
  };
}

const CHECK_STATUSES: readonly Check["status"][] = ["pass", "fail", "unknown"];

function parseCheck(raw: unknown): Check {
  const check = record(raw, "check");
  const measured = record(check.measured, "measured");
  return {
    name: text(check, "name"),
    status: oneOf(check, "status", CHECK_STATUSES),
    detail: text(check, "detail"),
    measured: Object.fromEntries(
      Object.keys(measured).map((key) => [key, number(measured, key)]),
    ),
    rule: text(check, "rule"),
  };
}

function parseAttempt(raw: unknown): Attempt {
  const attempt = record(raw, "attempt");
  const files = record(attempt.files, "files");
  return {
    number: number(attempt, "number"),
    status: oneOf(attempt, "status", VERDICTS),
    // Absent (the demo site's) or null (the API can't tell): none to show.
    checks:
      attempt.checks == null ? null : list(attempt, "checks").map(parseCheck),
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
    valuationNumber: optional(site, "valuation_number", text),
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
