import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JOB } from "@/lib/fixtures";

import { DesignPanel } from "./DesignPanel";

vi.mock("./ModelViewer", () => ({
  ModelViewer: ({ url }: { url: string }) => (
    <div data-testid="viewer">{url}</div>
  ),
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

  it("says why a job failed, in the API's words", async () => {
    serve(
      { ...JOB, status: "queued", accepted_attempt: null, attempts: [] },
      {
        ...JOB,
        status: "failed",
        accepted_attempt: null,
        attempts: [],
        error: "KeyError: MODEL_API_KEY is not set: get a Meta Model API key",
      },
    );
    render(<DesignPanel pollMs={5} />);
    await brief();
    expect(await screen.findByText(/MODEL_API_KEY is not set/)).toBeTruthy();
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

  it("needs a brief", async () => {
    serve();
    render(<DesignPanel pollMs={5} />);
    expect(
      (screen.getByRole("button", { name: "Design" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
