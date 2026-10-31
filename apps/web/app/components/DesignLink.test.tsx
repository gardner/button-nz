import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JOB } from "@/lib/fixtures";

import { DesignPanel } from "./DesignPanel";

vi.mock("./ModelViewer", () => ({
  ModelViewer: ({ url }: { url: string }) => (
    <div data-testid="viewer">{url}</div>
  ),
}));

function done(id: string, parent: string | null, instruction: string | null) {
  return {
    ...JOB,
    id,
    parent_id: parent,
    instruction,
    accepted_attempt: 1,
    attempts: [
      {
        number: 1,
        status: "pass",
        feedback: `Attempt 1 of ${id}.`,
        observations: [],
        files: { "design.glb": `/designs/${id}/attempts/1/design.glb` },
      },
    ],
  };
}

const ORIGINAL = done("abc123", null, null);
const MOVED = done("def456", "abc123", "Move it 3 m further from the street.");
const TURNED = done("ghi789", "def456", "Turn it to face north.");

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/** Answer each request with the next of `responses`, then never again. */
function serve(...responses: (object | Response)[]): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(() => new Promise<Response>(() => {}));
  for (const r of responses) {
    fetch.mockResolvedValueOnce(r instanceof Response ? r : respond(r));
  }
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function open(url: string): void {
  window.history.replaceState(null, "", url);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a link to a design", () => {
  it("opens the design it names, after the designs it revises", async () => {
    open("/?design=ghi789");
    const fetch = serve(TURNED, MOVED, ORIGINAL);
    render(<DesignPanel pollMs={5} />);
    const steps = await screen.findByRole("list", { name: "Design history" });
    expect(
      within(steps)
        .getAllByRole("listitem")
        .map((s) => s.textContent),
    ).toEqual([
      expect.stringMatching(/A small studio\./),
      expect.stringMatching(/Move it 3 m/),
      expect.stringMatching(/Turn it to face north/),
    ]);
    expect(screen.getByTestId("viewer").textContent).toBe(
      "/api/designs/ghi789/attempts/1/design.glb",
    );
    expect(fetch.mock.calls.map((c) => c[0])).toEqual([
      "/api/designs/ghi789",
      "/api/designs/def456",
      "/api/designs/abc123",
    ]);
  });

  it("says when the design it names can't be found", async () => {
    open("/?design=gone");
    serve(respond({ detail: "no design gone" }, 404));
    render(<DesignPanel pollMs={5} />);
    expect(
      await screen.findByText(/Could not open design gone: .*no design gone/),
    ).toBeTruthy();
  });

  it("is kept in the address bar for the design on show", async () => {
    serve(ORIGINAL, MOVED);
    render(<DesignPanel pollMs={5} />);
    await userEvent.type(screen.getByLabelText("Brief"), "A small studio.");
    await userEvent.click(screen.getByRole("button", { name: "Design" }));
    await screen.findByTestId("viewer");
    expect(window.location.search).toBe("?design=abc123");
    await userEvent.type(
      await screen.findByLabelText("Change this design"),
      "Move it 3 m further from the street.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Revise" }));
    await screen.findByRole("button", { name: /Move it 3 m/ });
    expect(window.location.search).toBe("?design=def456");
    await userEvent.click(
      screen.getByRole("button", { name: /A small studio\./ }),
    );
    expect(window.location.search).toBe("?design=abc123");
  });
});
