/**
 * Reading API responses: each field reader returns the typed value or throws
 * an ApiError naming the field, so a shape this app doesn't expect is caught
 * where it arrives.
 */

import type { Point } from "./api";

export class ApiError extends Error {
  /** The HTTP status, when the API answered with an error. */
  readonly status: number | undefined;

  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }

  /** Whether asking again could succeed: a server error, timeout or rate
   * limit. A client error (e.g. 404) or a response this app can't read (no
   * status: it would fail the same way again) is permanent. */
  get transient(): boolean {
    const s = this.status;
    return s !== undefined && (s >= 500 || s === 408 || s === 429);
  }
}

export type Fields = Record<string, unknown>;

export function isRecord(value: unknown): value is Fields {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function record(value: unknown, what: string): Fields {
  if (!isRecord(value)) throw new ApiError(`expected ${what} to be an object`);
  return value;
}

export function asText(value: unknown, what: string): string {
  if (typeof value !== "string")
    throw new ApiError(`expected ${what} to be text`);
  return value;
}

export function text(fields: Fields, key: string): string {
  return asText(fields[key], key);
}

export function number(fields: Fields, key: string): number {
  const value = fields[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiError(`expected ${key} to be a number`);
  }
  return value;
}

export function flag(fields: Fields, key: string): boolean {
  if (typeof fields[key] !== "boolean")
    throw new ApiError(`expected ${key} to be true or false`);
  return fields[key];
}

export function oneOf<T extends string>(
  fields: Fields,
  key: string,
  allowed: readonly T[],
): T {
  const value = text(fields, key);
  const found = allowed.find((a) => a === value);
  if (found === undefined)
    throw new ApiError(`unexpected ${key} ${JSON.stringify(value)}`);
  return found;
}

export function optional<T>(
  fields: Fields,
  key: string,
  read: (f: Fields, k: string) => T,
): T | null {
  return fields[key] === null ? null : read(fields, key);
}

export function asList(value: unknown, what: string): unknown[] {
  if (!Array.isArray(value))
    throw new ApiError(`expected ${what} to be a list`);
  return value;
}

export function list(fields: Fields, key: string): unknown[] {
  return asList(fields[key], key);
}

export function numbers(value: unknown, count: number): number[] {
  const values = asList(value, "coordinates");
  if (values.length !== count || !values.every((v) => typeof v === "number")) {
    throw new ApiError(`expected ${count} numbers`);
  }
  return values as number[];
}

export function asPoint(value: unknown): Point {
  return numbers(value, 2) as Point;
}
