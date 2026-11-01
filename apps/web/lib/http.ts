/** Requests to the button-nz API through the same-origin proxy at /api
 * (see next.config.ts): the JSON body, or an ApiError with the API's reason. */

import { ApiError, isRecord } from "./fields";

export const API = "/api";

export function send(
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

export async function request(
  path: string,
  init?: RequestInit,
): Promise<unknown> {
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
