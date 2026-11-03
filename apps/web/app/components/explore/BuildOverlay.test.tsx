import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { BuildProgress } from "@/lib/progress";
import type { SiteState } from "@/lib/sites";

import { BuildOverlay, SiteBuildView } from "./BuildOverlay";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FRAME: [number, number, number, number] = [1000, 2000, 1040, 2030];
const RING: [number, number][] = [
  [1010, 2010],
  [1020, 2010],
  [1020, 2020],
  [1010, 2010],
];
const NOTHING: BuildProgress = {
  frame: null,
  parcels: [],
  buildings: [],
  terrain: null,
  aerial: null,
  survey: null,
};
const PARCELS: BuildProgress = {
  ...NOTHING,
  frame: FRAME,
  parcels: [RING],
  buildings: [RING, RING],
};
const TERRAIN: BuildProgress = {
  ...PARCELS,
  terrain: { bbox: FRAME, lowM: 102.2, highM: 112.6, url: "/api/t.png" },
};
const SURVEYING: BuildProgress = {
  ...TERRAIN,
  aerial: { bbox: FRAME, url: "/api/a.png" },
  survey: {
    concepts: ["building", "tree", "car"],
    asking: "tree",
    found: [{ concept: "building", rings: [RING, RING] }],
  },
};

function overlay(progress: BuildProgress | null, step = "terrain") {
  const onDismiss = vi.fn();
  render(
    <BuildOverlay
      status="building"
      step={step as SiteState["step"]}
      error={null}
      progress={progress}
      onDismiss={onDismiss}
    />,
  );
  return onDismiss;
}

function layer(name: string): Element | null {
  return document.querySelector(`[data-layer="${name}"]`);
}

describe("BuildOverlay", () => {
  it("says what the build is doing before it has anything to show", () => {
    overlay(NOTHING, "parcels");
    const view = screen.getByRole("region", {
      name: "Your site, as it is built",
    });
    expect(view.textContent).toContain("Finding the title's parcels");
    expect(layer("parcels")).toBeNull();
  });

  it("draws the parcels and the buildings around them in the frame", () => {
    overlay(PARCELS);
    expect(layer("parcels")?.querySelectorAll("path")).toHaveLength(1);
    expect(layer("buildings")?.querySelectorAll("path")).toHaveLength(2);
    expect(document.querySelector("svg")?.getAttribute("viewBox")).toBe(
      "0 0 40 40",
    );
  });

  it("keeps every layer inside the frame the LiDAR and photo cover", () => {
    overlay(PARCELS);
    const clip = document.querySelector("clipPath rect");
    expect([clip?.getAttribute("y"), clip?.getAttribute("height")]).toEqual([
      "5",
      "30",
    ]);
    const clipped = document.querySelector("[data-layer=frame]");
    expect(clipped?.getAttribute("clip-path")).toBe(
      `url(#${document.querySelector("clipPath")?.id})`,
    );
    expect(clipped?.querySelector('[data-layer="parcels"]')).not.toBeNull();
  });

  it("shows the LiDAR's picture over its bbox, with its range of heights", () => {
    overlay(TERRAIN);
    const terrain = layer("terrain");
    expect(terrain?.getAttribute("href")).toBe("/api/t.png");
    expect(terrain?.getAttribute("y")).toBe("5");
    expect(terrain?.getAttribute("height")).toBe("30");
    expect(screen.getByText(/102–113 m/)).toBeTruthy();
  });

  it("shows what SAM 3.1 has found and what it is looking for now", () => {
    overlay(SURVEYING, "survey");
    expect(layer("aerial")?.getAttribute("href")).toBe("/api/a.png");
    expect(layer("found-building")?.querySelectorAll("path")).toHaveLength(2);
    expect(layer("scan")).not.toBeNull();
    const concepts = screen.getAllByRole("listitem");
    expect(concepts.map((c) => [c.textContent, c.dataset.state])).toEqual([
      ["building 2", "done"],
      ["tree", "asking"],
      ["car", "todo"],
    ]);
  });

  it("stops scanning once every concept is answered", () => {
    overlay({
      ...SURVEYING,
      survey: { ...SURVEYING.survey!, asking: null },
    });
    expect(layer("scan")).toBeNull();
  });

  it("stops scanning when the build stops partway through the survey", () => {
    render(
      <BuildOverlay
        status="failed"
        step={null}
        error="SAM 3.1 refused the request"
        progress={SURVEYING}
        onDismiss={() => {}}
      />,
    );
    expect(layer("scan")).toBeNull();
    const states = screen.getAllByRole("listitem").map((c) => c.dataset.state);
    expect(states).toEqual(["done", "todo", "todo"]);
  });

  it("can be dismissed", () => {
    const onDismiss = overlay(PARCELS);
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("says why a build stopped, beside what it had found", () => {
    render(
      <BuildOverlay
        status="no_lidar"
        step={null}
        error="no LINZ 1 m LiDAR covers this site"
        progress={PARCELS}
        onDismiss={() => {}}
      />,
    );
    const view = screen.getByRole("region", {
      name: "Your site, as it is built",
    });
    expect(view.textContent).toContain("No LiDAR here yet");
    expect(layer("parcels")).not.toBeNull();
  });
});

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

const WIRE_PARCELS = {
  frame: FRAME,
  parcels: [RING],
  buildings: [],
  terrain: null,
  aerial: null,
  survey: null,
};

function site(status: SiteState["status"]): SiteState {
  return {
    id: "s",
    address: "1 Test Street",
    status,
    step: status === "building" ? "terrain" : null,
    error: null,
    bounds: null,
    site: null,
  };
}

describe("SiteBuildView", () => {
  it("follows the build's progress while it builds", async () => {
    const fetch = vi.fn(() => Promise.resolve(respond(WIRE_PARCELS)));
    vi.stubGlobal("fetch", fetch);
    render(
      <SiteBuildView site={site("building")} pollMs={5} readyHoldMs={50} />,
    );
    await waitFor(() => expect(layer("parcels")).not.toBeNull());
    expect(fetch).toHaveBeenCalledWith("/api/sites/s/progress", undefined);
    await waitFor(() => expect(fetch.mock.calls.length).toBeGreaterThan(2));
  });

  it("never opens for a site that was ready when it was opened", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(<SiteBuildView site={site("ready")} pollMs={5} readyHoldMs={50} />);
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("says the site is ready, then steps aside", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respond(WIRE_PARCELS))),
    );
    const { rerender } = render(
      <SiteBuildView site={site("building")} pollMs={5} readyHoldMs={50} />,
    );
    await waitFor(() => expect(layer("parcels")).not.toBeNull());
    rerender(
      <SiteBuildView site={site("ready")} pollMs={5} readyHoldMs={50} />,
    );
    expect(screen.getByRole("region").textContent).toContain("Site ready");
    await waitFor(() => expect(screen.queryByRole("region")).toBeNull());
  });

  it("stays hidden once dismissed, as the build goes on", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respond(WIRE_PARCELS))),
    );
    const { rerender } = render(
      <SiteBuildView site={site("building")} pollMs={5} readyHoldMs={50} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("region")).toBeNull();
    await act(() => new Promise((r) => setTimeout(r, 20)));
    rerender(
      <SiteBuildView
        site={{ ...site("building"), step: "survey" }}
        pollMs={5}
        readyHoldMs={50}
      />,
    );
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("opens again when a site that stopped is built again", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(respond(WIRE_PARCELS))),
    );
    const { rerender } = render(
      <SiteBuildView site={site("failed")} pollMs={5} readyHoldMs={50} />,
    );
    expect(screen.queryByRole("region")).toBeNull();
    rerender(
      <SiteBuildView site={site("building")} pollMs={5} readyHoldMs={50} />,
    );
    await waitFor(() => expect(layer("parcels")).not.toBeNull());
  });

  it("opens again for a rebuild after it was dismissed", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    const { rerender } = render(
      <SiteBuildView site={site("building")} pollMs={5} readyHoldMs={50} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    rerender(
      <SiteBuildView site={site("failed")} pollMs={5} readyHoldMs={50} />,
    );
    expect(screen.queryByRole("region")).toBeNull();
    rerender(
      <SiteBuildView site={site("building")} pollMs={5} readyHoldMs={50} />,
    );
    expect(screen.getByRole("region")).not.toBeNull();
  });
});
