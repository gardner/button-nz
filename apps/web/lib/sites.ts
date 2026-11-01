/**
 * Any address's site (issue #86): finding an address, building its site, and
 * the town map. A site is built on the server from LINZ's open data, step by
 * step, and is ready once its LiDAR, aerial and survey are in.
 */

import { type Site, parseSite } from "./api";
import {
  asPoint,
  list,
  number,
  numbers,
  oneOf,
  optional,
  record,
  text,
} from "./fields";
import {
  type Bounds,
  type FeatureCollection,
  type LonLat,
  parseCollection,
} from "./geo";
import { request, send } from "./http";
import { type Tall, tall } from "./siteMap";

export interface Address {
  id: number; // LINZ address_id
  address: string;
  town: string;
  lonlat: LonLat;
}

export type SiteStatus = "building" | "ready" | "failed" | "no_lidar";
export type SiteStep = "parcels" | "terrain" | "aerial" | "survey";

const STATUSES: readonly SiteStatus[] = [
  "building",
  "ready",
  "failed",
  "no_lidar",
];
const STEPS: readonly SiteStep[] = ["parcels", "terrain", "aerial", "survey"];

export interface SiteState {
  id: string;
  address: string;
  status: SiteStatus;
  step: SiteStep | null; // what the server is doing now, while it builds
  error: string | null;
  bounds: Bounds | null; // lon/lat, once ready
  site: Site | null; // once ready
}

export type TownCategory = "clear" | "outlines" | "none";
const CATEGORIES: readonly TownCategory[] = ["clear", "outlines", "none"];

export interface TownSection {
  id: number;
  category: TownCategory; // a prefab fits clear today, on the outlines only, or not at all
}

export const MIN_QUERY = 3;

/** Addresses that start with `query`; none asked for under three letters. */
export async function searchAddresses(query: string): Promise<Address[]> {
  const q = query.trim();
  if (q.length < MIN_QUERY) return [];
  const body = record(
    await request(`/addresses?q=${encodeURIComponent(q)}`),
    "addresses",
  );
  return list(body, "addresses").map(parseAddress);
}

function parseAddress(raw: unknown): Address {
  const address = record(raw, "address");
  return {
    id: number(address, "id"),
    address: text(address, "address"),
    town: text(address, "town"),
    lonlat: asPoint(address.lonlat) as LonLat,
  };
}

/** Start building the site for an address (or find the one already built). */
export async function createSite(addressId: number): Promise<SiteState> {
  return parseSiteState(
    await send("POST", "/sites", { address_id: addressId }),
  );
}

export async function getSite(id: string): Promise<SiteState> {
  return parseSiteState(await request(`/sites/${encodeURIComponent(id)}`));
}

/** A site's state as #88 serves it: `{id, address, status, step, error}`,
 * and once ready, GET /site's fields beside them (its NZTM point as
 * `address_nztm`, since `address` is the text) with lon/lat `bounds`. */
export function parseSiteState(raw: unknown): SiteState {
  const state = record(raw, "site state");
  const status = oneOf(state, "status", STATUSES);
  const ready = status === "ready";
  const bounds = ready ? (numbers(state.bounds, 4) as Bounds) : null;
  const site = ready
    ? parseSite({ ...state, address: state.address_nztm })
    : null;
  return {
    id: text(state, "id"),
    address: text(state, "address"),
    status,
    step: optional(state, "step", (f, k) => oneOf(f, k, STEPS)),
    error: optional(state, "error", text),
    bounds,
    site,
  };
}

/** A town's screened sections, and the ones that can't be drawn. */
export interface Town {
  sections: FeatureCollection<TownSection>;
  buildings: FeatureCollection<Tall>; // LINZ outlines, as tall as the LiDAR says
  missing: { ids: number[]; reason: string }; // screened, but with no outline
}

/** A town's sections, coloured by the town screen (docs/results/town-screen). */
export async function getTown(slug: string): Promise<Town> {
  const raw = await request(`/town/${encodeURIComponent(slug)}`);
  const missing = record(record(raw, "town").missing, "missing");
  return {
    sections: parseCollection(raw, "town", (p) => ({
      id: number(p, "id"),
      category: oneOf(p, "category", CATEGORIES),
    })),
    buildings: parseCollection(
      record(raw, "town").buildings,
      "town buildings",
      tall,
    ),
    missing: {
      ids: list(missing, "ids").map((id) =>
        number({ "missing id": id }, "missing id"),
      ),
      reason: text(missing, "reason"),
    },
  };
}
