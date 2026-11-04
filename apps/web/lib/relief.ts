/**
 * A ready site's relief views (#149), as /sites/{id}/relief serves them:
 * its LINZ aerial photo lifted onto its own LiDAR heights, made when first
 * asked for, cheapest first (a depth map, a parallax clip, then a Blender
 * fly-over), each tier published the moment it ends.
 */

import { type Fields, asText, flag, list, oneOf, record, text } from "./fields";
import { API, request } from "./http";

const STATUSES = ["pending", "running", "ready", "failed"] as const;
export type TierStatus = (typeof STATUSES)[number];

export interface ReliefTier {
  tier: string; // "depth", "parallax" or "flyover"
  status: TierStatus;
  files: Record<string, string>; // what each file is, and its URL through the proxy
  error: string | null; // why it failed
}

export interface Relief {
  making: boolean; // still being made: ask again
  tiers: ReliefTier[];
}

/** A clip to play, and the still to show until it does. */
export interface Clip {
  tier: string;
  video: string;
  still: string;
}

const CLIPS = ["flyover", "parallax"]; // the better first

function path(siteId: string): string {
  return `/sites/${encodeURIComponent(siteId)}/relief`;
}

/** Start making the site's relief, unless it's made or being made. */
export async function startRelief(siteId: string): Promise<Relief> {
  return parseRelief(await request(path(siteId), { method: "POST" }));
}

export async function getRelief(siteId: string): Promise<Relief> {
  return parseRelief(await request(path(siteId)));
}

export function parseRelief(raw: unknown): Relief {
  const relief = record(raw, "relief");
  return {
    making: flag(relief, "making"),
    tiers: list(relief, "tiers").map((t) => tier(record(t, "tier"))),
  };
}

/** The best clip that's ready: the fly-over, else the parallax clip. */
export function shownClip(relief: Relief): Clip | null {
  for (const name of CLIPS) {
    const found = relief.tiers.find(
      (t) => t.tier === name && t.status === "ready",
    );
    if (found)
      return { tier: name, video: found.files.video, still: found.files.still };
  }
  return null;
}

function tier(fields: Fields): ReliefTier {
  const name = text(fields, "tier");
  const status = oneOf(fields, "status", STATUSES);
  const ready = status === "ready" ? record(fields.files, "files") : {};
  if (CLIPS.includes(name) && status === "ready") {
    text(ready, "video"); // a clip that's ready has both
    text(ready, "still");
  }
  return {
    tier: name,
    status,
    files: files(ready),
    error: status === "failed" ? text(fields, "error") : null,
  };
}

function files(fields: Fields): Record<string, string> {
  return Object.fromEntries(
    Object.entries(fields).map(([kind, url]) => [
      kind,
      `${API}${asText(url, kind)}`,
    ]),
  );
}
