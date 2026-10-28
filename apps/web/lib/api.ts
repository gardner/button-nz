/**
 * The button-nz API (Python, `button_nz.api`), reached through the
 * same-origin proxy at /api (see next.config.ts). Responses are checked as
 * they arrive: a shape this app doesn't expect is an ApiError, not a guess.
 */

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
  attempts: Attempt[];
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
}

export class ApiError extends Error {}

const JOB_STATUSES: readonly string[] = ["queued", "running", "done", "failed"];
const VERDICTS: readonly string[] = ["pass", "fail", "unknown", "error"];

export async function getSite(): Promise<Site> {
  return parseSite(await request("/site"));
}

export async function createDesign(
  brief: string,
  allowObservations: boolean,
): Promise<Job> {
  const body = JSON.stringify({ brief, allow_observations: allowObservations });
  return parseJob(
    await request("/designs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    }),
  );
}

export async function getDesign(id: string): Promise<Job> {
  return parseJob(await request(`/designs/${encodeURIComponent(id)}`));
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${API}${path}`, init);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      reason(body) ?? `${response.status} ${response.statusText}`,
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
    status: oneOf(job, "status", JOB_STATUSES) as JobStatus,
    createdAt: text(job, "created_at"),
    startedAt: optional(job, "started_at", text),
    finishedAt: optional(job, "finished_at", text),
    error: optional(job, "error", text),
    acceptedAttempt: optional(job, "accepted_attempt", number),
    attempts: list(job, "attempts").map(parseAttempt),
  };
}

function parseAttempt(raw: unknown): Attempt {
  const attempt = record(raw, "attempt");
  const files = record(attempt.files, "files");
  return {
    number: number(attempt, "number"),
    status: oneOf(attempt, "status", VERDICTS) as Verdict,
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

// Field readers: each returns the typed value or throws an ApiError naming it.

type Fields = Record<string, unknown>;

function isRecord(value: unknown): value is Fields {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown, what: string): Fields {
  if (!isRecord(value)) throw new ApiError(`expected ${what} to be an object`);
  return value;
}

function asText(value: unknown, what: string): string {
  if (typeof value !== "string")
    throw new ApiError(`expected ${what} to be text`);
  return value;
}

function text(fields: Fields, key: string): string {
  return asText(fields[key], key);
}

function number(fields: Fields, key: string): number {
  const value = fields[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiError(`expected ${key} to be a number`);
  }
  return value;
}

function flag(fields: Fields, key: string): boolean {
  if (typeof fields[key] !== "boolean")
    throw new ApiError(`expected ${key} to be true or false`);
  return fields[key];
}

function oneOf(
  fields: Fields,
  key: string,
  allowed: readonly string[],
): string {
  const value = text(fields, key);
  if (!allowed.includes(value))
    throw new ApiError(`unexpected ${key} ${JSON.stringify(value)}`);
  return value;
}

function optional<T>(
  fields: Fields,
  key: string,
  read: (f: Fields, k: string) => T,
): T | null {
  return fields[key] === null ? null : read(fields, key);
}

function asList(value: unknown, what: string): unknown[] {
  if (!Array.isArray(value))
    throw new ApiError(`expected ${what} to be a list`);
  return value;
}

function list(fields: Fields, key: string): unknown[] {
  return asList(fields[key], key);
}

function numbers(value: unknown, count: number): number[] {
  const values = asList(value, "coordinates");
  if (values.length !== count || !values.every((v) => typeof v === "number")) {
    throw new ApiError(`expected ${count} numbers`);
  }
  return values as number[];
}

function asPoint(value: unknown): Point {
  return numbers(value, 2) as Point;
}
