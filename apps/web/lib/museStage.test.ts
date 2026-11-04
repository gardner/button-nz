import { describe, expect, it } from "vitest";

import type { Attempt, Job, Live } from "./api";
import { NO_VIEWS, type ViewWatch, stageOf, watchViews } from "./museStage";

const FAILED: Attempt = {
  number: 1,
  status: "fail",
  checks: [
    {
      name: "floor_level",
      status: "fail",
      detail:
        "The floor is 1.24 m above the lowest ground. At most 1 m allowed.",
      measured: { height_above_lowest_m: 1.24 },
      rule: "Building Act 2004, Schedule 1A",
    },
  ],
  feedback: "floor_level: fail.",
  observations: ["inspect_elevation", "render_hillshade"],
  files: {
    "design.png": "/api/designs/j/attempts/1/design.png",
    "observation-2.png": "/api/designs/j/attempts/1/observation-2.png",
  },
};
const PASSED: Attempt = { ...FAILED, number: 2, status: "pass", checks: [] };

function live(
  phase: Live["phase"],
  observations: string[] = [],
  detail = "",
): Live {
  return { attempt: 2, phase, detail, observations };
}

function job(over: Partial<Job>): Job {
  return {
    id: "j",
    brief: "A studio.",
    allowObservations: true,
    status: "running",
    createdAt: "2026-11-04T00:00:00Z",
    startedAt: "2026-11-04T00:00:01Z",
    finishedAt: null,
    error: null,
    acceptedAttempt: null,
    parentId: null,
    instruction: null,
    siteId: "s",
    product: null,
    attempts: [],
    illustrating: false,
    live: null,
    ...over,
  };
}

const VIEW_1 = "/api/designs/j/attempts/2/observation-1.png";
const VIEW_2 = "/api/designs/j/attempts/2/observation-2.png";
const VIEW_3 = "/api/designs/j/attempts/2/observation-3.png";

describe("stageOf", () => {
  it("waits for a queued design, and for one not yet started", () => {
    expect(stageOf(job({ status: "queued" }), NO_VIEWS.names)).toEqual({
      kind: "waiting",
      queued: true,
    });
    expect(stageOf(job({}), NO_VIEWS.names)).toEqual({
      kind: "waiting",
      queued: false,
    });
  });

  it("thinks with nothing to show before the first attempt has made anything", () => {
    const first = { ...live("thinking"), attempt: 1 };
    expect(stageOf(job({ live: first }), NO_VIEWS.names)).toEqual({
      kind: "thinking",
    });
  });

  it("says which view is being drawn while Muse reads the LiDAR", () => {
    const j = job({
      attempts: [FAILED],
      live: live("observing", [], "render_contours"),
    });
    expect(stageOf(j, NO_VIEWS.names)).toEqual({
      kind: "reading",
      tool: "render_contours",
    });
  });

  it("shows the newest view while Muse thinks about it, named when the run said which it was", () => {
    const j = job({
      attempts: [FAILED],
      live: live("thinking", [VIEW_1, VIEW_3]),
    });
    expect(stageOf(j, new Map([[VIEW_3, "render_cross_section"]]))).toEqual({
      kind: "view",
      src: VIEW_3,
      attempt: 2,
      number: 3,
      tool: "render_cross_section",
    });
    expect(stageOf(j, NO_VIEWS.names)).toMatchObject({
      kind: "view",
      tool: null,
    });
  });

  it("shows the failed attempt while Muse fixes it, until it asks for a view", () => {
    const j = job({ attempts: [FAILED], live: live("thinking") });
    expect(stageOf(j, NO_VIEWS.names)).toEqual({
      kind: "fixing",
      attempt: FAILED,
    });
  });

  it("says Blender is building, then the rules are measured", () => {
    expect(stageOf(job({ live: live("rendering") }), NO_VIEWS.names)).toEqual({
      kind: "building",
    });
    expect(stageOf(job({ live: live("checking") }), NO_VIEWS.names)).toEqual({
      kind: "measuring",
    });
  });

  it("shows the accepted attempt, its visual once it has come, and whether one is coming", () => {
    const done = job({
      status: "done",
      acceptedAttempt: 2,
      attempts: [FAILED, PASSED],
    });
    expect(stageOf({ ...done, illustrating: true }, NO_VIEWS.names)).toEqual({
      kind: "accepted",
      attempt: PASSED,
      visual: null,
      illustrating: true,
    });
    const visual = "/api/designs/j/attempts/2/visual.png";
    const painted = {
      ...PASSED,
      files: { ...PASSED.files, "visual.png": visual },
    };
    expect(
      stageOf({ ...done, attempts: [FAILED, painted] }, NO_VIEWS.names),
    ).toEqual({
      kind: "accepted",
      attempt: painted,
      visual,
      illustrating: false,
    });
  });

  it("shows the last attempt of a run that stopped without a design, and why", () => {
    const failed = job({
      status: "failed",
      error: "Out of attempts.",
      attempts: [FAILED],
    });
    expect(stageOf(failed, NO_VIEWS.names)).toEqual({
      kind: "stopped",
      attempt: FAILED,
      error: "Out of attempts.",
    });
    expect(stageOf(job({ status: "done" }), NO_VIEWS.names)).toEqual({
      kind: "stopped",
      attempt: null,
      error: null,
    });
  });
});

describe("watchViews", () => {
  function poll(...lives: (Live | null)[]): ViewWatch {
    return lives.reduce<ViewWatch>(watchViews, NO_VIEWS);
  }

  it("names the view that lands after Muse was seen asking for it", () => {
    const watch = poll(
      live("observing", [], "render_contours"),
      live("observing", [], "render_contours"),
      live("thinking", [VIEW_1]),
    );
    expect(watch.names.get(VIEW_1)).toBe("render_contours");
  });

  it("names a view that lands as Muse asks for the next one", () => {
    const watch = poll(
      live("observing", [], "render_contours"),
      live("observing", [VIEW_1], "render_hillshade"),
      live("thinking", [VIEW_1, VIEW_2]),
    );
    expect(watch.names.get(VIEW_1)).toBe("render_contours");
    expect(watch.names.get(VIEW_2)).toBe("render_hillshade");
  });

  it("doesn't give a view the name of an ask that drew nothing, however late the next look", () => {
    // Exact heights are words, not a picture: ask 1 drew nothing, and
    // observation-2.png is an ask unseen between two looks (a throttled tab).
    const watch = poll(
      live("observing", [], "inspect_elevation"),
      live("thinking", [VIEW_2]),
    );
    expect(watch.names.size).toBe(0);
    // Nor when an unseen ask came between the views: observation-3 can't be
    // the hillshade asked for when observation-1 was the newest.
    expect(
      poll(
        live("observing", [], "render_contours"),
        live("observing", [VIEW_1], "render_hillshade"),
        live("thinking", [VIEW_1, VIEW_3]),
      ).names.get(VIEW_3),
    ).toBeUndefined();
  });

  it("doesn't carry an ask into the next attempt, whose views are numbered from 1 again", () => {
    const watch = poll(
      { ...live("observing", [], "render_contours"), attempt: 1 },
      // Unseen: attempt 1's view, its script, its checks; attempt 2's ask.
      live("thinking", [VIEW_1]), // attempt 2's observation-1.png
    );
    expect(watch.names.size).toBe(0);
  });

  it("doesn't name a later view after the asked one's own view was seen landing with the ask", () => {
    const watch = poll(
      live("thinking", []),
      live("observing", [VIEW_1], "render_contours"), // its own view, already there
      live("observing", [VIEW_1], "render_contours"),
      live("thinking", [VIEW_1, VIEW_2]),
    );
    expect(watch.names.get(VIEW_2)).toBeUndefined();
  });

  it("leaves unnamed what it can't be sure of: views there when it started, two at once, one after an unseen ask", () => {
    expect(poll(live("thinking", [VIEW_1])).names.size).toBe(0);
    expect(
      poll(
        live("observing", [], "render_contours"),
        live("thinking", [VIEW_1, VIEW_3]),
      ).names.size,
    ).toBe(0);
    // A view seen asked for made no picture (exact heights are words): the
    // next picture is another's.
    expect(
      poll(
        live("observing", [], "inspect_elevation"),
        live("thinking", []),
        live("thinking", [VIEW_1]),
      ).names.size,
    ).toBe(0);
  });
});
