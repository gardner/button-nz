import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JOB } from "@/lib/fixtures";

import { DesignDock } from "./explore/DesignDock";
import { HeroMedia } from "./explore/HeroMedia";
import { BeforeAfter } from "./Revisions";
import { useDesignChain } from "./useDesignChain";

/** The design dock as the explore page shows it, with the accepted design's
 * hero, and the before/after of a revision (the hero's compare tab) beside. */
function Dock({ pollMs }: { pollMs: number }) {
  const chain = useDesignChain(pollMs);
  const shown = chain.shown;
  const parent = chain.chain.find((j) => j.id === shown?.parentId);
  const accepted = shown?.status === "done" && shown.acceptedAttempt !== null;
  return (
    <>
      <DesignDock chain={chain} />
      {shown && accepted && <HeroMedia job={shown} parent={parent} />}
      {shown && parent && <BeforeAfter before={parent} after={shown} />}
    </>
  );
}

vi.mock("./ModelViewer", () => ({
  ModelViewer: ({ url }: { url: string }) => (
    <div data-testid="viewer">{url}</div>
  ),
}));

const MOVE = "Move it 3 m further from the street.";
const TURN = "Turn it to face north.";

function attempt(id: string, number: number, status = "pass") {
  return {
    number,
    status,
    feedback: `Attempt ${number} of ${id}.`,
    observations: [],
    files: {
      "design.glb": `/designs/${id}/attempts/${number}/design.glb`,
      "design.png": `/designs/${id}/attempts/${number}/design.png`,
    },
  };
}

const ORIGINAL = {
  ...JOB,
  accepted_attempt: 2,
  attempts: [JOB.attempts[0], attempt("abc123", 2, "unknown")],
};

/** A revision of design `parent`, done with attempt 1 accepted. */
function revision(id: string, parent: string, instruction: string) {
  return {
    ...JOB,
    id,
    parent_id: parent,
    instruction,
    accepted_attempt: 1,
    attempts: [attempt(id, 1)],
  };
}

const MOVED = revision("def456", "abc123", MOVE);
const TURNED = revision("ghi789", "def456", TURN);

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function design(): Promise<void> {
  await userEvent.type(
    screen.getByLabelText("What would you like to build?"),
    "A small studio.",
  );
  await userEvent.click(screen.getByRole("button", { name: "Design it" }));
}

async function revise(instruction: string): Promise<void> {
  await userEvent.type(
    await screen.findByLabelText("Change this design"),
    instruction,
  );
  await userEvent.click(screen.getByRole("button", { name: "Revise" }));
}

function history(): string[] {
  const steps = screen.getByRole("list", { name: "Design history" });
  return within(steps)
    .getAllByRole("listitem")
    .map((step) => step.textContent ?? "");
}

function source(alt: string | RegExp): string {
  return (screen.getByAltText(alt) as HTMLImageElement).src;
}

describe("revising a design", () => {
  it("offers a change only once a design has an accepted attempt", async () => {
    serve({ ...JOB, accepted_attempt: null });
    render(<Dock pollMs={5} />);
    await design();
    expect(
      await screen.findByText("No attempt passed every check."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Change this design")).toBeNull();
  });

  it("needs an instruction, as long as the API takes", async () => {
    serve(ORIGINAL);
    render(<Dock pollMs={5} />);
    await design();
    const field = (await screen.findByLabelText(
      "Change this design",
    )) as HTMLTextAreaElement;
    expect(field.maxLength).toBe(2000);
    const button = screen.getByRole("button", { name: "Revise" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(field, "   ");
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("follows the revision like a new design, then compares it with the one it changed", async () => {
    const fetch = serve(
      ORIGINAL,
      { ...MOVED, status: "queued", accepted_attempt: null, attempts: [] },
      {
        ...MOVED,
        status: "running",
        accepted_attempt: null,
        attempts: [attempt("def456", 1, "fail")],
      },
      MOVED,
    );
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    const [url, init] = fetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/designs/abc123/revisions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      instruction: MOVE,
      allow_observations: true, // as the design it changes
    });
    expect(await screen.findByText("Accepted: attempt 1")).toBeTruthy();
    expect(screen.getByTestId("viewer").textContent).toBe(
      "/api/designs/def456/attempts/1/design.glb",
    );
    expect(source(/^Before/)).toContain("/api/designs/abc123/attempts/2/");
    expect(source(/^After/)).toContain("/api/designs/def456/attempts/1/");
    expect(screen.getByText("Before")).toBeTruthy();
    expect(screen.getByText("After")).toBeTruthy();
    expect(history()).toEqual([
      expect.stringMatching(/A small studio\..*unknown/),
      expect.stringMatching(/Move it 3 m further.*pass/),
    ]);
  });

  it("revises a revision, building a chain", async () => {
    const fetch = serve(ORIGINAL, MOVED, TURNED);
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    await revise(TURN);
    expect(fetch.mock.calls[2][0]).toBe("/api/designs/def456/revisions");
    expect(await screen.findByAltText(/^After/)).toBeTruthy();
    expect(source(/^Before/)).toContain("/api/designs/def456/attempts/1/");
    expect(source(/^After/)).toContain("/api/designs/ghi789/attempts/1/");
    expect(history()).toEqual([
      expect.stringMatching(/A small studio\./),
      expect.stringMatching(/Move it 3 m/),
      expect.stringMatching(/Turn it to face north/),
    ]);
  });

  it("shows the step of the history that is selected", async () => {
    serve(ORIGINAL, MOVED);
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    await screen.findByAltText(/^After/);
    await userEvent.click(
      screen.getByRole("button", { name: /A small studio\./ }),
    );
    expect(screen.getByTestId("viewer").textContent).toBe(
      "/api/designs/abc123/attempts/2/design.glb",
    );
    expect(screen.getByAltText("Attempt 1 render")).toBeTruthy();
    expect(screen.queryByAltText(/^Before/)).toBeNull();
    const original = screen.getByRole("button", { name: /A small studio\./ });
    expect(original.getAttribute("aria-current")).toBe("step");
    await userEvent.click(screen.getByRole("button", { name: /Move it 3 m/ }));
    expect(screen.getByAltText(/^Before/)).toBeTruthy();
  });

  it("still shows a design's visual when it was revised before the visual came", async () => {
    const drawn = {
      ...ORIGINAL,
      attempts: [
        JOB.attempts[0],
        {
          ...attempt("abc123", 2, "unknown"),
          files: {
            ...attempt("abc123", 2, "unknown").files,
            "visual.json": "/designs/abc123/attempts/2/visual.json",
            "visual.png": "/designs/abc123/attempts/2/visual.png",
          },
        },
      ],
    };
    let revised = false; // the original's visual comes only after it is revised
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        revised = url.endsWith("/revisions");
        return respond(revised ? MOVED : { ...ORIGINAL, illustrating: true });
      }
      if (url.includes("abc123"))
        return respond(revised ? drawn : { ...ORIGINAL, illustrating: true });
      return respond(MOVED);
    });
    vi.stubGlobal("fetch", fetch);
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE); // straight away, while the original's visual is being made
    await screen.findByAltText(/^After/);
    await vi.waitFor(() =>
      expect(
        fetch.mock.calls.some(([u, i]) => !i && String(u).includes("abc123")),
      ).toBe(true),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /A small studio\./ }),
    );
    await userEvent.click(
      await screen.findByRole("tab", { name: "AI visual" }),
    );
    expect(
      await screen.findByAltText("AI illustration of the accepted design"),
    ).toBeTruthy();
  });

  it("follows one design at a time", async () => {
    serve(ORIGINAL, { ...MOVED, status: "queued", attempts: [] });
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    expect(await screen.findByText("Queued…")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Design it" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("says why a revision failed and keeps the design it changed", async () => {
    serve(ORIGINAL, {
      ...MOVED,
      status: "failed",
      accepted_attempt: null,
      attempts: [],
      error: "Blender exited with status 1",
    });
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    expect(
      await screen.findByText(/The design run failed: Blender exited/),
    ).toBeTruthy();
    expect(history()[1]).toMatch(/failed/);
    expect(screen.queryByLabelText("Change this design")).toBeNull();
    await userEvent.click(
      screen.getByRole("button", { name: /A small studio\./ }),
    );
    expect(screen.getByTestId("viewer").textContent).toBe(
      "/api/designs/abc123/attempts/2/design.glb",
    );
    expect(screen.getByLabelText("Change this design")).toBeTruthy();
  });

  it("changes an earlier step after a failed revision, and says which", async () => {
    const fetch = serve(
      ORIGINAL,
      { ...MOVED, status: "failed", accepted_attempt: null, attempts: [] },
      revision("ghi789", "abc123", TURN),
    );
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    await screen.findByText(/The design run failed/);
    await userEvent.click(
      screen.getByRole("button", { name: /A small studio\./ }),
    );
    await revise(TURN);
    expect(fetch.mock.calls[2][0]).toBe("/api/designs/abc123/revisions");
    expect(await screen.findByAltText(/^After/)).toBeTruthy();
    expect(source(/^Before/)).toContain("/api/designs/abc123/attempts/2/");
    expect(history()[2]).toMatch(/Change to step 1: Turn it to face north/);
  });

  it("says when no attempt of a revision was accepted", async () => {
    serve(ORIGINAL, {
      ...MOVED,
      accepted_attempt: null,
      attempts: [attempt("def456", 1, "fail")],
    });
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    expect(
      await screen.findByText("No attempt passed every check."),
    ).toBeTruthy();
    expect(history()[1]).toMatch(/nothing accepted/);
    expect(source(/^Before/)).toContain("/api/designs/abc123/attempts/2/");
    expect(screen.queryByAltText(/^After/)).toBeNull();
    expect(screen.getByText("Nothing was accepted.")).toBeTruthy();
  });

  it("says why a design can't be revised, keeping the instruction", async () => {
    const detail = "design abc123 has no accepted attempt to revise";
    serve(ORIGINAL, respond({ detail }, 409));
    render(<Dock pollMs={5} />);
    await design();
    await revise(MOVE);
    expect(await screen.findByText(detail)).toBeTruthy();
    const field = screen.getByLabelText(
      "Change this design",
    ) as HTMLTextAreaElement;
    expect(field.value).toBe(MOVE);
    expect(screen.queryByRole("list", { name: "Design history" })).toBeNull();
  });
});
