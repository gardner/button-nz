import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JOB } from "@/lib/fixtures";

import { DesignPanel } from "./DesignPanel";

const viewer = vi.hoisted(() => ({ fails: false }));

vi.mock("./ModelViewer", () => ({
  ModelViewer: ({ url }: { url: string }) => {
    if (viewer.fails) throw new Error("no WebGL");
    return <div data-testid="viewer">{url}</div>;
  },
}));

const FAILED_ATTEMPT = JOB.attempts[0];
const ACCEPTED_ATTEMPT = {
  number: 2,
  status: "unknown",
  feedback: "No check failed. building_separation: unknown.",
  observations: [],
  files: {
    "design.glb": "/designs/abc123/attempts/2/design.glb",
    "design.png": "/designs/abc123/attempts/2/design.png",
  },
};

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function serve(...bodies: unknown[]): ReturnType<typeof vi.fn> {
  const fetch = vi.fn();
  for (const body of bodies) fetch.mockResolvedValueOnce(respond(body));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  viewer.fails = false;
  cleanup();
  vi.unstubAllGlobals();
});

async function brief(text = "A small studio."): Promise<void> {
  await userEvent.type(screen.getByLabelText("Brief"), text);
  await userEvent.click(screen.getByRole("button", { name: "Design" }));
}

describe("DesignPanel", () => {
  it("shows each attempt as it finishes, then the accepted concept in 3D", async () => {
    serve(
      { ...JOB, status: "queued", accepted_attempt: null, attempts: [] },
      {
        ...JOB,
        status: "running",
        accepted_attempt: null,
        attempts: [FAILED_ATTEMPT],
      },
      { ...JOB, attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT] },
    );
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(await screen.findByText(/0\.50 m from the boundary/)).toBeTruthy();
    expect(await screen.findByText("Accepted: attempt 2")).toBeTruthy();
    expect(screen.getByTestId("viewer").textContent).toBe(
      "/api/designs/abc123/attempts/2/design.glb",
    );
    const render1 = screen.getByAltText("Attempt 1 render") as HTMLImageElement;
    expect(render1.src).toContain("/api/designs/abc123/attempts/1/design.png");
    expect(screen.getByText("render_contours")).toBeTruthy();
  });

  it("shows an AI illustration, labelled for what it is, beside the render", async () => {
    const illustrated = {
      ...ACCEPTED_ATTEMPT,
      files: {
        ...ACCEPTED_ATTEMPT.files,
        "visual.png": "/designs/abc123/attempts/2/visual.png",
      },
    };
    serve({ ...JOB, attempts: [FAILED_ATTEMPT, illustrated] });
    render(<DesignPanel pollMs={5} />);
    await brief();
    const visual = (await screen.findByAltText(
      "AI illustration of attempt 2",
    )) as HTMLImageElement;
    expect(visual.src).toContain("/api/designs/abc123/attempts/2/visual.png");
    const caption = visual.closest("figure")?.textContent ?? "";
    expect(caption).toMatch(/AI-illustrated/);
    expect(caption).toMatch(/only the new dwelling's position and shape/i);
    expect(screen.queryByAltText("AI illustration of attempt 1")).toBeNull();
  });

  it("keeps looking for the AI illustration after the design is done", async () => {
    const withVisual = {
      ...ACCEPTED_ATTEMPT,
      files: {
        ...ACCEPTED_ATTEMPT.files,
        "visual.json": "/designs/abc123/attempts/2/visual.json",
        "visual.png": "/designs/abc123/attempts/2/visual.png",
      },
    };
    const fetch = serve(
      // done; the API says the visual is still being made
      {
        ...JOB,
        illustrating: true,
        attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT],
      },
      { ...JOB, attempts: [FAILED_ATTEMPT, withVisual] },
    );
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(
      await screen.findByAltText("AI illustration of attempt 2"),
    ).toBeTruthy();
    await new Promise((r) => setTimeout(r, 50));
    expect(fetch).toHaveBeenCalledTimes(2); // then it stops: visual.json says how it went
  });

  it("leaves the forms usable while the visual is being made", async () => {
    serve(
      {
        ...JOB,
        illustrating: true,
        attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT],
      },
      {
        ...JOB,
        illustrating: true,
        attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT],
      },
    );
    render(<DesignPanel pollMs={50} />);
    await brief();
    await userEvent.type(
      await screen.findByLabelText("Change this design"),
      "Move it back.",
    );
    expect(screen.getByRole("button", { name: "Revise" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.getByRole("button", { name: "Design" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("gives each design its own wait for a visual", async () => {
    const other = { ...JOB, id: "def456" };
    const withVisual = {
      ...ACCEPTED_ATTEMPT,
      files: {
        ...ACCEPTED_ATTEMPT.files,
        "visual.json": "/designs/def456/attempts/2/visual.json",
        "visual.png": "/designs/def456/attempts/2/visual.png",
      },
    };
    let stuckPolls = 0;
    const stuck = {
      ...JOB,
      illustrating: true,
      attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT],
    };
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        const first =
          fetch.mock.calls.filter(([, i]) => i?.method === "POST").length === 1;
        return respond(
          first
            ? stuck
            : {
                ...other,
                illustrating: true,
                attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT],
              },
        );
      }
      if (url.includes("abc123")) {
        stuckPolls += 1; // its visual never comes: the server stopped mid-visual
        return respond(stuck);
      }
      return respond({ ...other, attempts: [FAILED_ATTEMPT, withVisual] });
    });
    vi.stubGlobal("fetch", fetch);
    render(<DesignPanel pollMs={1} />);
    await brief();
    await vi.waitFor(() => expect(stuckPolls).toBe(90), { timeout: 5000 });
    await userEvent.click(screen.getByRole("button", { name: "Design" }));
    expect(
      await screen.findByAltText("AI illustration of attempt 2"),
    ).toBeTruthy();
  });

  it("says why a job failed, in the API's words", async () => {
    serve(
      { ...JOB, status: "queued", accepted_attempt: null, attempts: [] },
      {
        ...JOB,
        status: "failed",
        accepted_attempt: null,
        attempts: [],
        error: "KeyError: META_API_KEY is not set: get a Meta Model API key",
      },
    );
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(await screen.findByText(/META_API_KEY is not set/)).toBeTruthy();
    expect(screen.queryByTestId("viewer")).toBeNull();
  });

  it("sends whether the model may request LiDAR observations", async () => {
    const fetch = serve({ ...JOB, status: "done", attempts: [] });
    render(<DesignPanel pollMs={5} />);
    await userEvent.click(
      screen.getByLabelText("Let the model request LiDAR views"),
    );
    await brief();
    const init = fetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body)).allow_observations).toBe(false);
  });

  it("keeps polling after a failed poll and clears the error", async () => {
    const fetch = vi.fn();
    fetch.mockResolvedValueOnce(
      respond({
        ...JOB,
        status: "queued",
        accepted_attempt: null,
        attempts: [],
      }),
    );
    fetch.mockResolvedValueOnce(respond({ detail: "Bad Gateway" }, 502));
    fetch.mockResolvedValueOnce(
      respond({ ...JOB, attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT] }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(await screen.findByText("Accepted: attempt 2")).toBeTruthy();
    expect(screen.queryByText("Bad Gateway")).toBeNull();
  });

  it("stops following a design the API no longer has", async () => {
    const fetch = vi.fn();
    fetch.mockResolvedValueOnce(
      respond({
        ...JOB,
        status: "queued",
        accepted_attempt: null,
        attempts: [],
      }),
    );
    fetch.mockResolvedValue(respond({ detail: "no design abc123" }, 404));
    vi.stubGlobal("fetch", fetch);
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(await screen.findByText(/no design abc123/)).toBeTruthy();
    await new Promise((r) => setTimeout(r, 50));
    expect(fetch).toHaveBeenCalledTimes(2); // the POST and one poll: no retries
    const design = screen.getByRole("button", {
      name: "Design",
    }) as HTMLButtonElement;
    expect(design.disabled).toBe(false);
  });

  it("stops following a design the API answers with a shape it can't read", async () => {
    const fetch = vi.fn();
    fetch.mockResolvedValueOnce(
      respond({
        ...JOB,
        status: "queued",
        accepted_attempt: null,
        attempts: [],
      }),
    );
    fetch.mockResolvedValue(respond({ ...JOB, status: "cancelled" }));
    vi.stubGlobal("fetch", fetch);
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(await screen.findByText(/unexpected status/)).toBeTruthy();
    await new Promise((r) => setTimeout(r, 50));
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("keeps the run on the page when the 3D model can't load", async () => {
    serve({ ...JOB, attempts: [FAILED_ATTEMPT, ACCEPTED_ATTEMPT] });
    viewer.fails = true;
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(
      await screen.findByText(/Could not show the 3D model: no WebGL/),
    ).toBeTruthy();
    expect(screen.getByText("Attempt 1")).toBeTruthy();
  });

  it("sends one design however often Design is clicked", async () => {
    let finish: (r: Response) => void = () => {};
    const fetch = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<DesignPanel pollMs={5} />);
    await userEvent.type(screen.getByLabelText("Brief"), "A small studio.");
    const design = screen.getByRole("button", { name: "Design" });
    await userEvent.dblClick(design);
    await userEvent.click(design);
    expect(fetch).toHaveBeenCalledTimes(1);
    finish(respond({ ...JOB, status: "done", attempts: [] }));
    expect(await screen.findByText("Accepted: attempt 2")).toBeTruthy();
  });

  it("needs a brief", async () => {
    serve();
    render(<DesignPanel pollMs={5} />);
    expect(
      (screen.getByRole("button", { name: "Design" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
