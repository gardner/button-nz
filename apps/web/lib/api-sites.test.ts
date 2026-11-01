import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDesign,
  decideFeature,
  getFeatures,
  parseJob,
  setBuildingsComplete,
} from "./api";
import { ApiError } from "./fields";
import { JOB, SURVEY } from "./fixtures";
import { CHECKS } from "./fixtures-sites";

function serve(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => vi.unstubAllGlobals());

const WITH_CHECKS = {
  ...JOB,
  site_id: "35-victory-street-reefton",
  attempts: JOB.attempts.map((a) => ({ ...a, checks: CHECKS })),
};

describe("a design on a site", () => {
  it("reads its site and each attempt's checks", () => {
    const job = parseJob(WITH_CHECKS);
    expect(job.siteId).toBe("35-victory-street-reefton");
    expect(job.attempts[0].checks).toEqual([
      {
        name: "title_boundary_setback",
        status: "pass",
        detail: "3.20 m from the title boundary; at least 2 m required.",
        measured: { value: 3.2, minimum: 2 },
        rule: "Building Act 2004, Schedule 1A",
      },
      expect.objectContaining({ status: "unknown" }),
      expect.objectContaining({ status: "fail" }),
    ]);
  });

  it("has no checks or site when the API sends none (the demo site's API)", () => {
    const job = parseJob(JOB);
    expect(job.siteId).toBeNull();
    expect(job.attempts[0].checks).toBeNull();
  });

  it.each([
    [{ ...CHECKS[0], status: "maybe" }],
    [{ ...CHECKS[0], measured: { value: "3.2" } }],
    [{ ...CHECKS[0], rule: undefined }],
  ])("refuses a check it can't show", (check) => {
    const raw = {
      ...WITH_CHECKS,
      attempts: [{ ...WITH_CHECKS.attempts[0], checks: [check] }],
    };
    expect(() => parseJob(raw)).toThrow(ApiError);
  });

  it("asks for a design on a site", async () => {
    const fetch = serve(WITH_CHECKS, 202);
    await createDesign("A studio.", true, undefined, "addr-1907458");
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual({
      brief: "A studio.",
      allow_observations: true,
      site_id: "addr-1907458",
    });
  });
});

describe("a site's survey", () => {
  it("is read and decided at the site's own address", async () => {
    const fetch = serve(SURVEY);
    await getFeatures("addr-1907458");
    expect(fetch.mock.calls[0][0]).toBe("/api/sites/addr-1907458/features");
    serve(SURVEY.features[0]);
    await decideFeature("s1", "1", "ignore", "addr-1907458");
    expect(vi.mocked(fetch).mock.calls.length).toBe(1);
    const decide = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(decide[0]).toBe("/api/sites/addr-1907458/features/1");
    serve({ survey_id: "s1", buildings_complete: true });
    await setBuildingsComplete("s1", true, "addr-1907458");
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe(
      "/api/sites/addr-1907458/survey",
    );
  });

  it("is the demo site's without a site", async () => {
    const fetch = serve(SURVEY);
    await getFeatures();
    expect(fetch.mock.calls[0][0]).toBe("/api/site/features");
  });
});
