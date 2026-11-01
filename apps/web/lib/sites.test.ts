import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./fields";
import { ADDRESSES, SITE_BUILDING, SITE_READY, TOWN } from "./fixtures-sites";
import {
  createSite,
  createSiteFromSection,
  getSite,
  getTown,
  parseSiteState,
  searchAddresses,
} from "./sites";

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function serve(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetch = vi.fn().mockResolvedValue(respond(body, status));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

describe("searchAddresses", () => {
  it("asks for the typed text and reads each address", async () => {
    const fetch = serve(ADDRESSES);
    const found = await searchAddresses("35 Victory");
    expect(fetch.mock.calls[0][0]).toBe("/api/addresses?q=35%20Victory");
    expect(found[0]).toEqual({
      id: 1907458,
      address: "35 Victory Street, Reefton",
      town: "Reefton",
      lonlat: [171.8622, -42.1158],
    });
  });

  it("ranks addresses near where the map looks first", async () => {
    const fetch = serve(ADDRESSES);
    await searchAddresses("10 Broadway", [171.862234, -42.115318]);
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/addresses?q=10%20Broadway&near=171.8622%2C-42.1153",
    );
  });

  it("wraps a map centre that has panned past the antimeridian", async () => {
    const fetch = serve(ADDRESSES);
    await searchAddresses("10 Broadway", [183.5, -44.0]);
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/addresses?q=10%20Broadway&near=-176.5000%2C-44.0000",
    );
  });

  it("doesn't ask for fewer than three letters", async () => {
    const fetch = serve(ADDRESSES);
    expect(await searchAddresses("35")).toEqual([]);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("sites", () => {
  it("starts building the site for an address", async () => {
    const fetch = serve(SITE_BUILDING, 202);
    const site = await createSite(1907458);
    expect(fetch.mock.calls[0][0]).toBe("/api/sites");
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual({
      address_id: 1907458,
    });
    expect(site).toMatchObject({
      status: "building",
      step: "terrain",
      site: null,
    });
  });

  it("starts building the site for a section, by its parcel", async () => {
    const fetch = serve(SITE_BUILDING, 202);
    await createSiteFromSection(3652040);
    expect(fetch.mock.calls[0][0]).toBe("/api/sites");
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual({
      parcel_id: 3652040,
    });
  });

  it("reads a ready site with its bounds and the site itself", async () => {
    serve(SITE_READY);
    const site = await getSite("35-victory-street-reefton");
    expect(site.status).toBe("ready");
    expect(site.address).toBe("35 Victory Street, Reefton");
    expect(site.bounds).toEqual([171.8619, -42.1161, 171.8625, -42.1155]);
    expect(site.site).toMatchObject({
      title: "354613",
      valuationNumber: null,
      address: [1505941.6, 5336793.7],
    });
  });

  it.each([
    [{ ...SITE_BUILDING, status: "paused" }],
    [{ ...SITE_BUILDING, step: "dreaming" }],
    [{ ...SITE_READY, bounds: undefined }],
    [{ ...SITE_READY, address_nztm: undefined }],
    [{ ...SITE_READY, crs: "EPSG:4326" }],
  ])("refuses a site state it doesn't expect", (raw) => {
    expect(() => parseSiteState(raw)).toThrow(ApiError);
  });

  it("reads a site with no LiDAR, and why", () => {
    const site = parseSiteState({
      ...SITE_BUILDING,
      status: "no_lidar",
      step: null,
      error: "LINZ has no 1 m LiDAR here",
    });
    expect(site).toMatchObject({
      status: "no_lidar",
      error: "LINZ has no 1 m LiDAR here",
    });
  });
});

describe("getTown", () => {
  it("reads each section's category", async () => {
    const fetch = serve(TOWN);
    const town = await getTown("reefton");
    expect(fetch.mock.calls[0][0]).toBe("/api/town/reefton");
    expect(town.missing).toEqual({
      ids: [],
      reason: "not in LINZ's NZ Primary Parcels",
    });
    expect(town.buildings.features.map((f) => f.properties)).toEqual([
      { baseM: null, heightM: null },
      { baseM: 0, heightM: 6.5 },
    ]);
    expect(town.sections.features.map((f) => f.properties.category)).toEqual([
      "clear",
      "outlines",
      "none",
    ]);
  });

  it("refuses a town that doesn't say which sections are missing", async () => {
    serve({ ...TOWN, missing: undefined });
    await expect(getTown("reefton")).rejects.toThrow(ApiError);
  });

  it("refuses a category it doesn't know", async () => {
    serve({
      ...TOWN,
      features: [
        {
          ...TOWN.features[0],
          properties: { id: 1, property: 1, category: "maybe" },
        },
      ],
    });
    await expect(getTown("reefton")).rejects.toThrow(/category/);
  });

  it("refuses a section with no property", async () => {
    serve({
      ...TOWN,
      features: [
        { ...TOWN.features[0], properties: { id: 1, category: "clear" } },
      ],
    });
    await expect(getTown("reefton")).rejects.toThrow(/property/);
  });
});
