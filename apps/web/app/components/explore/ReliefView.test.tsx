import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReliefView } from "./ReliefView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

const PARALLAX = {
  tier: "parallax",
  status: "ready",
  files: {
    still: "/sites/s/relief/parallax.png",
    video: "/sites/s/relief/parallax.mp4",
  },
};
const FLYOVER = {
  tier: "flyover",
  status: "ready",
  files: {
    still: "/sites/s/relief/flyover.png",
    video: "/sites/s/relief/flyover.mp4",
  },
};
const RENDERING = { tier: "flyover", status: "running" };

/** The API's answers in turn, the last one again for every later ask. */
function answers(...bodies: unknown[]) {
  const fetch = vi.fn(() =>
    Promise.resolve(respond(bodies.length > 1 ? bodies.shift() : bodies[0])),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function video(): HTMLVideoElement | null {
  return document.querySelector("video");
}

describe("ReliefView", () => {
  it("asks for nothing until it's asked to", () => {
    const fetch = answers({ making: false, tiers: [] });
    render(<ReliefView siteId="s" pollMs={5} />);
    expect(screen.getByRole("button", { name: "See it in 3D" })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows the parallax clip as soon as it's ready, then the fly-over", async () => {
    // The API answers with the relief as it is now; the test moves it on.
    let now: unknown = { making: true, tiers: [] };
    const fetch = vi.fn(() => Promise.resolve(respond(now)));
    vi.stubGlobal("fetch", fetch);
    render(<ReliefView siteId="s" pollMs={5} />);
    fireEvent.click(screen.getByRole("button", { name: "See it in 3D" }));
    expect(fetch).toHaveBeenCalledWith("/api/sites/s/relief", {
      method: "POST",
    });
    await waitFor(() => expect(fetch.mock.calls.length).toBeGreaterThan(1));
    now = { making: true, tiers: [PARALLAX, RENDERING] };
    await waitFor(() =>
      expect(video()?.getAttribute("src")).toBe(
        "/api/sites/s/relief/parallax.mp4",
      ),
    );
    const clip = video()!;
    expect(clip.muted && clip.loop && clip.autoplay).toBe(true);
    expect(clip.hasAttribute("playsinline")).toBe(true);
    const view = screen.getByRole("figure");
    expect(view.textContent).toContain(
      "its LINZ aerial photo on its own LiDAR heights; walls are not seen from above",
    );
    expect(view.textContent).toContain("rendering the fly-over");
    now = { making: false, tiers: [PARALLAX, FLYOVER] };
    await waitFor(() =>
      expect(video()?.getAttribute("src")).toBe(
        "/api/sites/s/relief/flyover.mp4",
      ),
    );
    expect(video()?.getAttribute("poster")).toBe(
      "/api/sites/s/relief/flyover.png",
    );
    const calls = fetch.mock.calls.length;
    await new Promise((done) => setTimeout(done, 30));
    expect(fetch.mock.calls.length).toBe(calls); // made: no more asking
  });

  it("says why a view couldn't be made, and keeps the one that was", async () => {
    const broken = { tier: "flyover", status: "failed", error: "no GPU" };
    answers({ making: false, tiers: [PARALLAX, broken] });
    render(<ReliefView siteId="s" pollMs={5} />);
    fireEvent.click(screen.getByRole("button", { name: "See it in 3D" }));
    await waitFor(() =>
      expect(screen.getByText(/The fly-over couldn't be made: no GPU/)),
    );
    expect(video()?.getAttribute("src")).toBe(
      "/api/sites/s/relief/parallax.mp4",
    );
  });

  it("says so when the API refuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(respond({ detail: "site s is building" }, 409)),
      ),
    );
    render(<ReliefView siteId="s" pollMs={5} />);
    fireEvent.click(screen.getByRole("button", { name: "See it in 3D" }));
    await waitFor(() =>
      expect(
        screen.getByText(/Couldn't show it in 3D: site s is building/),
      ).toBeTruthy(),
    );
  });
});
