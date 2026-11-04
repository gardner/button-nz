import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type Attempt, type Job, type Phase, parseJob } from "@/lib/api";
import { JOB } from "@/lib/fixtures";

import { MuseAtWork } from "./MuseAtWork";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const REEFTON = {
  id: "35-victory-street-reefton",
  address: "35 Victory Street, Reefton",
};
const WESTPORT = {
  id: "12-main-road-westport",
  address: "12 Main Road, Westport",
};
const VIEW = "/api/designs/j/attempts/2/observation-1.png";

/** A running job: attempt 1 failed a check, attempt 2 is under way. */
function running(phase: Phase, detail = "", views = [VIEW]): Job {
  const job = parseJob(JOB);
  return {
    ...job,
    status: "running",
    acceptedAttempt: null,
    attempts: [{ ...job.attempts[0], number: 1, status: "fail" }],
    live: { attempt: 2, phase, detail, observations: views },
  };
}

const MEASURED: Attempt = {
  number: 1,
  status: "fail",
  feedback: "floor_level: fail.",
  observations: [],
  files: { "design.png": "/api/designs/j/attempts/1/design.png" },
  checks: [
    {
      name: "title_boundary_setback",
      status: "pass",
      detail: "3.38 m from the title boundary; at least 2 m required.",
      measured: { distance_m: 3.38, required_m: 2 },
      rule: "Building Act 2004, Schedule 1A",
    },
    {
      name: "floor_level",
      status: "fail",
      detail:
        "The floor is 1.24 m above the lowest ground. At most 1 m allowed.",
      measured: { height_above_lowest_m: 1.24 },
      rule: "Building Act 2004, Schedule 1A",
    },
  ],
};

function overlay(): HTMLElement {
  return screen.getByRole("region", { name: "Muse at work" });
}

/** The small panel of today: the overlay hidden. */
function small(job: Job): HTMLElement {
  vi.stubGlobal("fetch", () => new Promise(() => {})); // the prefab list
  render(<MuseAtWork job={job} place={REEFTON} />);
  fireEvent.click(screen.getByRole("button", { name: "Hide" }));
  return overlay();
}

describe("MuseAtWork, large", () => {
  it("opens large while a design runs; × takes it back to the small panel, which can open it again", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    render(<MuseAtWork job={running("rendering")} place={REEFTON} />);
    expect(overlay().className).toContain("fixed");
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("button", { name: "Hide" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show large" }));
    expect(screen.getByRole("button", { name: "Hide" })).toBeTruthy();
  });

  it("doesn't open for a design that was done before it was shown", () => {
    const { container } = render(
      <MuseAtWork job={parseJob(JOB)} place={REEFTON} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("says which view is being drawn, then shows it full size, named", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    const { rerender } = render(
      <MuseAtWork
        job={running("observing", "render_cross_section", [])}
        place={REEFTON}
      />,
    );
    expect(overlay().textContent).toMatch(/Muse asked for a cross-section/);
    rerender(<MuseAtWork job={running("thinking")} place={REEFTON} />);
    const view = screen.getByRole("img", {
      name: "LiDAR view 1 of attempt 2: a cross-section",
    });
    expect(view.getAttribute("src")).toBe(VIEW);
  });

  it("numbers each view as its attempt does, on the stage and in the filmstrip alike", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    const job = running("thinking");
    job.attempts[0] = {
      ...job.attempts[0],
      files: {
        "design.png": "/api/designs/j/attempts/1/design.png",
        "observation-2.png": "/api/designs/j/attempts/1/observation-2.png",
        "observation-3.png": "/api/designs/j/attempts/1/observation-3.png",
      },
    };
    render(<MuseAtWork job={job} place={REEFTON} />);
    const names = screen
      .getAllByRole("img", { name: /LiDAR view|render/ })
      .map((i) => i.getAttribute("alt"));
    expect(names).toEqual([
      "LiDAR view 1 of attempt 2", // the stage
      "LiDAR view 2 of attempt 1", // the filmstrip, in order
      "LiDAR view 3 of attempt 1",
      "Attempt 1's render: failed a check",
      "LiDAR view 1 of attempt 2",
    ]);
  });

  it("shows what failed and by how much, then that Muse is fixing it", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    const job = { ...running("thinking", "", []), attempts: [MEASURED] };
    render(<MuseAtWork job={job} place={REEFTON} />);
    const stage = within(overlay());
    expect(
      stage.getByRole("img", { name: "Attempt 1 as Blender rendered it" }),
    ).toBeTruthy();
    expect(stage.getAllByText(/1\.24 m above the lowest ground/)).toBeTruthy();
    expect(stage.getByText(/Muse is fixing it/)).toBeTruthy();
    const checks = stage.getByRole("list", { name: "Attempt 1's checks" });
    const items = within(checks).getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringMatching(/✓.*2 m from the boundary.*3\.38 m/),
      expect.stringMatching(/✗.*Floor 1 m up or less.*1\.24 m/),
    ]);
  });

  it("stays open as the design is accepted, and shows Muse Image's visual when it arrives", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    const { rerender } = render(
      <MuseAtWork job={running("checking")} place={REEFTON} />,
    );
    const passed = { ...MEASURED, number: 2, status: "pass" as const };
    const done: Job = {
      ...running("checking"),
      status: "done",
      live: null,
      acceptedAttempt: 2,
      attempts: [MEASURED, passed],
      illustrating: true,
    };
    rerender(<MuseAtWork job={done} place={REEFTON} />);
    expect(overlay().textContent).toMatch(/Muse Image is painting/);
    expect(overlay().textContent).toMatch(/Accepted: attempt 2/);
    expect(
      screen.getByRole("img", { name: "Attempt 2 as Blender rendered it" }),
    ).toBeTruthy();
    const visual = "/api/designs/j/attempts/2/visual.png";
    const painted = {
      ...passed,
      files: { ...passed.files, "visual.png": visual },
    };
    rerender(
      <MuseAtWork
        job={{ ...done, illustrating: false, attempts: [MEASURED, painted] }}
        place={REEFTON}
      />,
    );
    const image = screen.getByRole("img", {
      name: "AI illustration of the accepted design",
    });
    expect(image.getAttribute("src")).toBe(visual);
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("region", { name: "Muse at work" })).toBeNull();
  });

  it("rotates sourced housing facts while Muse thinks, with Reefton's figures only in Reefton", () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    const first = { ...running("thinking", "", []), attempts: [] };
    const { unmount } = render(<MuseAtWork job={first} place={REEFTON} />);
    const facts = () => screen.getByRole("region", { name: "Housing facts" });
    expect(facts().textContent).toMatch(/622 of 959/);
    expect(facts().textContent).toMatch(
      /Source: Button NZ town screen, docs\/results\/town-screen/,
    );
    act(() => vi.advanceTimersByTime(10_000));
    expect(facts().textContent).toMatch(/439 Reefton backyards/);
    unmount();
    render(<MuseAtWork job={first} place={WESTPORT} />);
    expect(facts().textContent).toMatch(/Schedule 1A/);
    act(() => vi.advanceTimersByTime(30_000));
    expect(facts().textContent).not.toMatch(/Reefton/);
  });

  it("shows no facts while Blender builds", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    render(<MuseAtWork job={running("rendering")} place={REEFTON} />);
    expect(overlay().textContent).toMatch(/Blender builds and renders it/);
    expect(screen.queryByRole("region", { name: "Housing facts" })).toBeNull();
  });
});

describe("MuseAtWork, small", () => {
  it("lights the step the run is on, and says what Muse is looking at", () => {
    const panel = small(running("observing", "render_contours"));
    expect(within(panel).getByText(/Attempt 2/)).toBeTruthy();
    const current = within(panel).getByRole("listitem", { current: "step" });
    expect(current.textContent).toMatch(/LiDAR/);
    expect(current.textContent).toMatch(/contours/);
  });

  it("fills a filmstrip with the views made and each attempt's render and verdict", () => {
    small(running("rendering"));
    const views = screen.getAllByRole("img", { name: /LiDAR view/ });
    expect(views[0].getAttribute("src")).toBe(VIEW);
    const render1 = screen.getByRole("img", {
      name: /Attempt 1's render: failed a check/,
    });
    expect(render1.getAttribute("src")).toContain("design.png");
    const current = screen.getByRole("listitem", { current: "step" });
    expect(current.textContent).toMatch(/Blender/);
  });

  it("keeps a finished attempt's LiDAR views in the filmstrip, before its render", () => {
    const job = running("thinking");
    job.attempts[0] = {
      ...job.attempts[0],
      files: {
        "design.png": "/api/designs/j/attempts/1/design.png",
        "observation-2.png": "/api/designs/j/attempts/1/observation-2.png",
        "observation-1.png": "/api/designs/j/attempts/1/observation-1.png",
      },
    };
    small(job);
    const srcs = screen.getAllByRole("img").map((i) => i.getAttribute("src"));
    expect(srcs).toEqual([
      "/api/designs/j/attempts/1/observation-1.png",
      "/api/designs/j/attempts/1/observation-2.png",
      "/api/designs/j/attempts/1/design.png",
      VIEW,
    ]);
  });

  it("says Muse is deciding, not writing, while it is asked its next move", () => {
    small(running("thinking"));
    const current = screen.getByRole("listitem", { current: "step" });
    expect(current.textContent).toMatch(/decides its next move/);
  });

  it("says a queued design is waiting its turn", () => {
    const job = {
      ...parseJob(JOB),
      status: "queued" as const,
      attempts: [],
      live: null,
    };
    small(job);
    expect(screen.getByText(/Waiting for a free designer/)).toBeTruthy();
  });
});
