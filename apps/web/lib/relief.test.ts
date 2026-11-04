import { describe, expect, it } from "vitest";

import { ApiError } from "./fields";
import { parseRelief, shownClip } from "./relief";

const PARALLAX = {
  tier: "parallax",
  status: "ready",
  files: {
    still: "/sites/s/relief/parallax.png",
    video: "/sites/s/relief/parallax.mp4",
  },
  facts: { frames: 60 },
  seconds: 2.1,
};
const FLYOVER = {
  tier: "flyover",
  status: "ready",
  files: {
    still: "/sites/s/relief/flyover.png",
    video: "/sites/s/relief/flyover.mp4",
  },
  facts: { frames: 96 },
  seconds: 9.8,
};

describe("parseRelief", () => {
  it("reads a relief not yet asked for", () => {
    expect(parseRelief({ making: false, tiers: [] })).toEqual({
      making: false,
      tiers: [],
    });
  });

  it("reads each tier, its files through the proxy and why one failed", () => {
    const relief = parseRelief({
      making: true,
      tiers: [
        PARALLAX,
        { tier: "flyover", status: "failed", error: "no GPU", seconds: 0.1 },
        { tier: "depth", status: "pending" },
      ],
    });
    expect(relief.making).toBe(true);
    expect(relief.tiers).toEqual([
      {
        tier: "parallax",
        status: "ready",
        files: {
          still: "/api/sites/s/relief/parallax.png",
          video: "/api/sites/s/relief/parallax.mp4",
        },
        error: null,
      },
      { tier: "flyover", status: "failed", files: {}, error: "no GPU" },
      { tier: "depth", status: "pending", files: {}, error: null },
    ]);
  });

  it("refuses a reply that isn't a relief", () => {
    expect(() => parseRelief({ tiers: [] })).toThrow(ApiError);
    expect(() =>
      parseRelief({ making: false, tiers: [{ tier: "x", status: "done" }] }),
    ).toThrow(ApiError);
    expect(() =>
      parseRelief({
        making: false,
        tiers: [{ ...PARALLAX, files: { video: 3 } }],
      }),
    ).toThrow(ApiError);
    expect(() =>
      parseRelief({
        making: false,
        tiers: [{ tier: "flyover", status: "failed" }],
      }),
    ).toThrow(ApiError);
  });
});

describe("shownClip", () => {
  it("is nothing until a clip is ready", () => {
    expect(shownClip({ making: true, tiers: [] })).toBeNull();
    const pending = parseRelief({
      making: true,
      tiers: [{ tier: "parallax", status: "running" }],
    });
    expect(shownClip(pending)).toBeNull();
  });

  it("is the parallax clip first, and the fly-over once it's ready", () => {
    const rendering = parseRelief({
      making: true,
      tiers: [PARALLAX, { tier: "flyover", status: "running" }],
    });
    expect(shownClip(rendering)).toEqual({
      tier: "parallax",
      video: "/api/sites/s/relief/parallax.mp4",
      still: "/api/sites/s/relief/parallax.png",
    });
    const flown = parseRelief({ making: false, tiers: [PARALLAX, FLYOVER] });
    expect(shownClip(flown)?.tier).toBe("flyover");
    expect(shownClip(flown)?.video).toBe("/api/sites/s/relief/flyover.mp4");
  });
});
