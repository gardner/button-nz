import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JOB, PRODUCTS } from "@/lib/fixtures";

import { DesignPanel } from "./DesignPanel";

vi.mock("./ModelViewer", () => ({
  ModelViewer: ({ url }: { url: string }) => (
    <div data-testid="viewer">{url}</div>
  ),
}));

const VISTA = {
  id: "airhome-vista",
  name: "AirHome Vista",
  length_m: 12.2,
  width_m: 4,
};
const PLACING = {
  ...JOB,
  id: "def456",
  status: "queued",
  accepted_attempt: null,
  attempts: [],
  product: VISTA,
};

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("placing a real prefab", () => {
  it("designs again with the same brief, placing the chosen product", async () => {
    const fetch = vi.fn(() => new Promise<Response>(() => {}));
    for (const body of [JOB, PRODUCTS, PLACING]) {
      fetch.mockResolvedValueOnce(respond(body));
    }
    vi.stubGlobal("fetch", fetch);
    render(<DesignPanel pollMs={5} />);
    await userEvent.type(screen.getByLabelText("Brief"), "A small studio.");
    await userEvent.click(screen.getByRole("button", { name: "Design" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Which real prefabs fit?" }),
    );
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Place the AirHome Vista on the site",
      }),
    );
    expect(
      await screen.findByText("Placing the AirHome Vista: walls 12.2 × 4 m"),
    ).toBeTruthy();
    const [url, init] = fetch.mock.calls[2] as unknown as [string, RequestInit];
    expect(url).toBe("/api/designs");
    expect(JSON.parse(String(init.body))).toEqual({
      brief: "A small studio.",
      allow_observations: true,
      product_id: "airhome-vista",
    });
  });
});
