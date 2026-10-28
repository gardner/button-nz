import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createDesign,
  getDesign,
  getSite,
  parseJob,
  parseSite,
} from "./api";
import { JOB } from "./fixtures";

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseJob", () => {
  it("reads a job and its attempts", () => {
    const job = parseJob(JOB);
    expect(job.status).toBe("done");
    expect(job.acceptedAttempt).toBe(2);
    expect(job.attempts[0].observations).toEqual(["render_contours"]);
    expect(job.attempts[0].files["design.png"]).toBe(
      "/api/designs/abc123/attempts/1/design.png",
    );
  });

  it.each([
    [{ ...JOB, status: "paused" }],
    [{ ...JOB, attempts: [{ number: "1" }] }],
    [{ ...JOB, id: 7 }],
    [null],
  ])("rejects a malformed job", (raw) => {
    expect(() => parseJob(raw)).toThrow(ApiError);
  });
});

describe("the client", () => {
  it("queues a design through the same-origin proxy", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(respond({ ...JOB, status: "queued" }, 202));
    vi.stubGlobal("fetch", fetch);
    const job = await createDesign("A small studio.", false);
    expect(job.status).toBe("queued");
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/designs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      brief: "A small studio.",
      allow_observations: false,
    });
  });

  it("reports the API's reason and status for an error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respond({ detail: "no design nope" }, 404)),
    );
    const error = await getDesign("nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("no design nope");
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).transient).toBe(false);
  });

  it("refuses a site that isn't in NZTM", () => {
    expect(() => parseSite({ crs: "EPSG:4326" })).toThrow("EPSG:2193");
  });

  it("reads the site", async () => {
    const site = {
      name: "35 Victory Street, Reefton",
      title: "354613",
      valuation_number: "1905027200",
      crs: "EPSG:2193",
      address: [1505941.6, 5336793.7],
      extent: [1505926.13, 5336777.48, 1505969.74, 5336822.22],
      parcels: {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: 3652040,
            properties: { appellation: "Section 700 Town of Reefton" },
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [0, 0],
                  [1, 0],
                  [1, 1],
                  [0, 0],
                ],
              ],
            },
          },
        ],
      },
      sources: {
        dem: {
          title: "West Coast LiDAR 1m DEM",
          licence: "CC-BY-4.0",
          attribution: "Toitū Te Whenua LINZ",
          capture: {
            start: "2020-05-15T12:00:00Z",
            end: "2024-07-10T12:00:00Z",
          },
        },
      },
      open_items: ["Confirm the boundary pegs."],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(site)));
    const parsed = await getSite();
    expect(parsed.parcels[0].appellation).toBe("Section 700 Town of Reefton");
    expect(parsed.parcels[0].ring).toHaveLength(4);
    expect(parsed.sources[0]).toMatchObject({
      key: "dem",
      licence: "CC-BY-4.0",
    });
    expect(parsed.openItems).toEqual(["Confirm the boundary pegs."]);
  });
});
