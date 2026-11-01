import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { type Job, type Phase, parseJob } from "@/lib/api";
import { JOB } from "@/lib/fixtures";

import { MuseAtWork } from "./MuseAtWork";

afterEach(cleanup);

/** A running job: attempt 1 failed a check, attempt 2 is looking at the LiDAR. */
function running(phase: Phase, detail = ""): Job {
  const job = parseJob(JOB);
  return {
    ...job,
    status: "running",
    acceptedAttempt: null,
    attempts: [{ ...job.attempts[0], number: 1, status: "fail" }],
    live: {
      attempt: 2,
      phase,
      detail,
      observations: ["/api/designs/j/attempts/2/observation-1.png"],
    },
  };
}

describe("MuseAtWork", () => {
  it("lights the step the run is on, and says what Muse is looking at", () => {
    render(<MuseAtWork job={running("observing", "render_contours")} />);
    const panel = screen.getByRole("region", { name: "Muse at work" });
    expect(within(panel).getByText(/Attempt 2/)).toBeTruthy();
    const current = within(panel).getByRole("listitem", { current: "step" });
    expect(current.textContent).toMatch(/LiDAR/);
    expect(current.textContent).toMatch(/contours/);
  });

  it("fills a filmstrip with the views made and each attempt's render and verdict", () => {
    render(<MuseAtWork job={running("rendering")} />);
    const views = screen.getAllByRole("img", { name: /LiDAR view/ });
    expect(views[0].getAttribute("src")).toBe(
      "/api/designs/j/attempts/2/observation-1.png",
    );
    const render1 = screen.getByRole("img", {
      name: /Attempt 1's render: failed a check/,
    });
    expect(render1.getAttribute("src")).toContain("design.png");
    const current = screen.getByRole("listitem", { current: "step" });
    expect(current.textContent).toMatch(/Blender/);
  });

  it("says a queued design is waiting its turn", () => {
    const job = {
      ...parseJob(JOB),
      status: "queued" as const,
      attempts: [],
      live: null,
    };
    render(<MuseAtWork job={job} />);
    expect(screen.getByText(/Waiting for a free designer/)).toBeTruthy();
  });
});
