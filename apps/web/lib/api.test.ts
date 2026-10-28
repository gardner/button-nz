import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createDesign,
  decideFeature,
  getDesign,
  getFeatures,
  getSite,
  parseJob,
  parseSite,
  reviseDesign,
  setBuildingsComplete,
} from "./api";
import { JOB, SURVEY } from "./fixtures";

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
    expect(job.parentId).toBeNull();
    expect(job.instruction).toBeNull();
  });

  it("reads which design a revision changes, and how", () => {
    const job = parseJob({
      ...JOB,
      parent_id: "xyz789",
      instruction: "Move it 3 m further from the street.",
    });
    expect(job.parentId).toBe("xyz789");
    expect(job.instruction).toBe("Move it 3 m further from the street.");
  });

  it.each([
    [{ ...JOB, status: "paused" }],
    [{ ...JOB, attempts: [{ number: "1" }] }],
    [{ ...JOB, id: 7 }],
    [{ ...JOB, parent_id: 7 }],
    [{ ...JOB, instruction: undefined }],
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

  it("asks for a revision of a design", async () => {
    const revision = {
      ...JOB,
      id: "def456",
      status: "queued",
      parent_id: "abc123",
      instruction: "Move it 3 m further from the street.",
    };
    const fetch = vi.fn().mockResolvedValue(respond(revision, 202));
    vi.stubGlobal("fetch", fetch);
    const job = await reviseDesign(
      "abc123",
      "Move it 3 m further from the street.",
      true,
    );
    expect(job.parentId).toBe("abc123");
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/designs/abc123/revisions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      instruction: "Move it 3 m further from the street.",
      allow_observations: true,
    });
  });

  it("reports why a design can't be revised", async () => {
    const detail = "design abc123 has no accepted attempt to revise";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond({ detail }, 409)));
    const error = await reviseDesign("abc123", "Bigger.", true).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe(detail);
    expect((error as ApiError).status).toBe(409);
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

describe("the survey client", () => {
  it("reads the surveyed features", async () => {
    const fetch = vi.fn().mockResolvedValue(respond(SURVEY));
    vi.stubGlobal("fetch", fetch);
    const survey = await getFeatures();
    expect(fetch.mock.calls[0][0]).toBe("/api/site/features");
    expect(survey.features.map((f) => f.concept)).toEqual([
      "shed",
      "tree",
      "unlabelled",
    ]);
  });

  it("records a decision and reads back the feature", async () => {
    const tree = SURVEY.features[1];
    const decided = {
      ...tree,
      properties: { ...tree.properties, decision: "keep_clear" },
    };
    const fetch = vi.fn().mockResolvedValue(respond(decided));
    vi.stubGlobal("fetch", fetch);
    const feature = await decideFeature("s1", "2", "keep_clear");
    expect(feature.decision).toBe("keep_clear");
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/site/features/2");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({
      decision: "keep_clear",
      survey_id: "s1", // the survey it was made on: a newer one is refused
    });
  });

  it("says every building is listed", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        respond({ survey_id: "s1", buildings_complete: true }),
      );
    vi.stubGlobal("fetch", fetch);
    expect(await setBuildingsComplete("s1", true)).toBe(true);
    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/site/survey");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({
      buildings_complete: true,
      survey_id: "s1",
    });
  });

  it("reports why the list can't be complete yet", async () => {
    const detail = "decide what these are first: 2, 3";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond({ detail }, 409)));
    const error = await setBuildingsComplete("s1", true).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe(detail);
    expect((error as ApiError).status).toBe(409);
  });
});
