import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { JOB, SURVEY } from "@/lib/fixtures";
import {
  ADDRESSES,
  CHECKS,
  DESIGN_MAP,
  SITE_MAP,
  SITE_READY,
  TOWN,
} from "@/lib/fixtures-sites";

import { FakeMap } from "../map/fakeMap";
import { Explore } from "./Explore";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../map/fakeMap");
  return { Map: fake.FakeMap, Marker: fake.FakeMarker, setWorkerUrl: () => {} };
});
vi.mock("../ModelViewer", () => ({
  ModelViewer: ({ url }: { url: string }) => (
    <div data-testid="viewer">{url}</div>
  ),
}));

const SITE = "35-victory-street-reefton";
const ACCEPTED = {
  ...JOB,
  site_id: SITE,
  attempts: [
    {
      number: 1,
      status: "unknown",
      feedback: "No check failed.",
      observations: [],
      files: {
        "design.png": "/designs/abc123/attempts/1/design.png",
        "design.glb": "/designs/abc123/attempts/1/design.glb",
        "visual.png": "/designs/abc123/attempts/1/visual.png",
      },
      checks: CHECKS.slice(0, 2),
    },
  ],
  accepted_attempt: 1,
};

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function serve(routes: Record<string, unknown>): ReturnType<typeof vi.fn> {
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const body = routes[`${init?.method ?? "GET"} ${url.split("?")[0]}`];
    return body === undefined
      ? new Promise<Response>(() => {})
      : Promise.resolve(respond(body));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  FakeMap.last = null;
  document.body.innerHTML = "";
});

function open() {
  window.history.replaceState(null, "", `/?site=${SITE}`);
}

describe("a ready site", () => {
  it("draws its rules and survey on the map, and lists what was found", async () => {
    open();
    serve({
      "GET /api/town/reefton": TOWN,
      [`GET /api/sites/${SITE}`]: SITE_READY,
      [`GET /api/sites/${SITE}/map`]: SITE_MAP,
      [`GET /api/sites/${SITE}/features`]: SURVEY,
    });
    render(<Explore pollMs={5} />);
    expect(await screen.findByText("What's on the site?")).toBeTruthy();
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("site-room-fill")).toBe(true),
    );
    for (const layer of [
      "site-setback-fill",
      "site-parcels-line",
      "site-features-fill",
    ])
      expect(FakeMap.last?.layers.has(layer)).toBe(true);
    act(() => FakeMap.last?.click("site-features-fill", 0));
    expect(
      screen.getByRole("group", { name: "What is #1 shed?" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("listitem", { current: "step" }).textContent,
    ).toContain("Survey");
  });

  it("designs from a brief, then shows the checks, the walls on the map and the 3D", async () => {
    open();
    const fetch = serve({
      "GET /api/town/reefton": TOWN,
      [`GET /api/sites/${SITE}`]: SITE_READY,
      [`GET /api/sites/${SITE}/map`]: SITE_MAP,
      [`GET /api/sites/${SITE}/features`]: SURVEY,
      "POST /api/designs": ACCEPTED,
      "GET /api/designs/abc123/map": DESIGN_MAP,
    });
    render(<Explore pollMs={5} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /afternoon sun/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Design it" }));
    expect(await screen.findByText("Accepted: attempt 1")).toBeTruthy();
    const posted = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(posted?.[1]?.body))).toMatchObject({
      brief: "A one-bedroom studio that gets the afternoon sun",
      site_id: SITE,
    });
    const badges = within(
      screen.getByRole("list", { name: "Checks" }),
    ).getAllByRole("listitem");
    expect(badges.map((b) => b.textContent)).toEqual([
      "✓ 2 m from the boundary",
      "? 2 m from buildings",
    ]);
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("design-walls-fill")).toBe(true),
    );
    await vi.waitFor(() =>
      expect(
        document.querySelector('[data-label="distance"]')?.textContent,
      ).toBe("3.2 m ≥ 2 m"),
    );
    expect(screen.getByTestId("viewer").textContent).toBe(
      "/api/designs/abc123/attempts/1/design.glb",
    );
    fireEvent.click(screen.getByRole("tab", { name: "AI visual" }));
    expect(
      screen.getByAltText("AI illustration of the accepted design"),
    ).toBeTruthy();
    expect(
      screen.getByRole("listitem", { current: "step" }).textContent,
    ).toContain("Check");
  });

  it("says a design's checks may not hold once the survey changes, and drops a site map that can't refresh", async () => {
    window.history.replaceState(null, "", `/?site=${SITE}&design=abc123`);
    let maps = 0;
    const fetch = vi.fn((url: string, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${url.split("?")[0]}`;
      const body: Record<string, unknown> = {
        "GET /api/town/reefton": TOWN,
        [`GET /api/sites/${SITE}`]: SITE_READY,
        [`GET /api/sites/${SITE}/features`]: SURVEY,
        [`PUT /api/sites/${SITE}/features/2`]: {
          ...SURVEY.features[1],
          properties: {
            ...SURVEY.features[1].properties,
            decision: "building",
          },
        },
        "GET /api/designs/abc123": ACCEPTED,
        "GET /api/designs/abc123/map": DESIGN_MAP,
      };
      if (route === `GET /api/sites/${SITE}/map`)
        return Promise.resolve(
          ++maps === 1 ? respond(SITE_MAP) : respond({ detail: "down" }, 503),
        );
      return body[route] === undefined
        ? new Promise<Response>(() => {})
        : Promise.resolve(respond(body[route]));
    });
    vi.stubGlobal("fetch", fetch);
    render(<Explore pollMs={5} />);
    expect(await screen.findByText("Accepted: attempt 1")).toBeTruthy();
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("site-features-fill")).toBe(true),
    );
    expect(screen.queryByText(/survey changed/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: /#2 tree/ }));
    fireEvent.click(
      within(screen.getByRole("group", { name: /#2 tree/ })).getByRole(
        "button",
        { name: "Existing building" },
      ),
    );
    expect(
      await screen.findByText(/survey changed after this design/),
    ).toBeTruthy();
    expect(await screen.findByText(/site's map couldn't load/)).toBeTruthy();
    expect(FakeMap.last?.layers.has("site-features-fill")).toBe(false);
  });

  it("keeps a newer design's link when a slow link to another site's design answers", async () => {
    window.history.replaceState(null, "", `/?site=${SITE}&design=other1`);
    let answer: (r: Response) => void = () => {};
    const fetch = vi.fn((url: string, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${url.split("?")[0]}`;
      if (route === "GET /api/designs/other1")
        return new Promise<Response>((r) => (answer = r));
      const body = {
        "GET /api/town/reefton": TOWN,
        [`GET /api/sites/${SITE}`]: SITE_READY,
        [`GET /api/sites/${SITE}/map`]: SITE_MAP,
        [`GET /api/sites/${SITE}/features`]: SURVEY,
        "POST /api/designs": ACCEPTED,
        "GET /api/designs/abc123/map": DESIGN_MAP,
      }[route];
      return body === undefined
        ? new Promise<Response>(() => {})
        : Promise.resolve(respond(body));
    });
    vi.stubGlobal("fetch", fetch);
    render(<Explore pollMs={5} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /afternoon sun/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Design it" }));
    expect(await screen.findByText("Accepted: attempt 1")).toBeTruthy();
    await vi.waitFor(() =>
      expect(window.location.search).toContain("design=abc123"),
    );
    answer(respond({ ...ACCEPTED, id: "other1", site_id: "another-site" }));
    await new Promise((r) => setTimeout(r, 30));
    expect(window.location.search).toContain("design=abc123");
    expect(screen.getByText("Accepted: attempt 1")).toBeTruthy();
  });

  it("holds the shown site's controls while another address is being opened", async () => {
    open();
    serve({
      "GET /api/town/reefton": TOWN,
      [`GET /api/sites/${SITE}`]: SITE_READY,
      [`GET /api/sites/${SITE}/map`]: SITE_MAP,
      [`GET /api/sites/${SITE}/features`]: SURVEY,
      "GET /api/addresses": ADDRESSES,
      // POST /sites never answers: the new address is still on its way.
    });
    render(<Explore pollMs={5} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /afternoon sun/ }),
    );
    const design = screen.getByRole("button", { name: "Design it" });
    expect(design.matches(":disabled")).toBe(false);
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    fireEvent.click(
      await screen.findByRole("option", { name: /35 Victory Road, Laingholm/ }),
    );
    await vi.waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Design it" }).matches(":disabled"),
      ).toBe(true),
    );
    expect(
      screen.getByText(/Opening 35 Victory Road, Laingholm, Auckland/),
    ).toBeTruthy();
  });

  it("doesn't blame a newer design for an older link that failed", async () => {
    window.history.replaceState(null, "", `/?site=${SITE}&design=gone1`);
    let answer: (r: Response) => void = () => {};
    const fetch = vi.fn((url: string, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${url.split("?")[0]}`;
      if (route === "GET /api/designs/gone1")
        return new Promise<Response>((r) => (answer = r));
      const body = {
        "GET /api/town/reefton": TOWN,
        [`GET /api/sites/${SITE}`]: SITE_READY,
        [`GET /api/sites/${SITE}/map`]: SITE_MAP,
        [`GET /api/sites/${SITE}/features`]: SURVEY,
        "POST /api/designs": ACCEPTED,
        "GET /api/designs/abc123/map": DESIGN_MAP,
      }[route];
      return body === undefined
        ? new Promise<Response>(() => {})
        : Promise.resolve(respond(body));
    });
    vi.stubGlobal("fetch", fetch);
    render(<Explore pollMs={5} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /afternoon sun/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Design it" }));
    expect(await screen.findByText("Accepted: attempt 1")).toBeTruthy();
    await vi.waitFor(() =>
      expect(window.location.search).toContain("design=abc123"),
    );
    answer(respond({ detail: "no design gone1" }, 404));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText(/Could not open design gone1/)).toBeNull();
  });

  it("doesn't open a design linked from another site", async () => {
    window.history.replaceState(null, "", `/?site=${SITE}&design=abc123`);
    serve({
      "GET /api/town/reefton": TOWN,
      [`GET /api/sites/${SITE}`]: SITE_READY,
      [`GET /api/sites/${SITE}/map`]: SITE_MAP,
      [`GET /api/sites/${SITE}/features`]: SURVEY,
      "GET /api/designs/abc123": { ...ACCEPTED, site_id: "another-site" },
    });
    render(<Explore pollMs={5} />);
    expect(await screen.findByText("What's on the site?")).toBeTruthy();
    await vi.waitFor(() =>
      expect(window.location.search).toBe(`?site=${SITE}`),
    );
    expect(screen.queryByText(/Accepted: attempt/)).toBeNull();
  });

  it("doesn't ask for a new site when a surveyed feature is clicked", async () => {
    open();
    const fetch = serve({
      "GET /api/town/reefton": TOWN,
      [`GET /api/sites/${SITE}`]: SITE_READY,
      [`GET /api/sites/${SITE}/map`]: SITE_MAP,
      [`GET /api/sites/${SITE}/features`]: SURVEY,
    });
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("site-features-fill")).toBe(true),
    );
    act(() => FakeMap.last?.click("town-fill", 0)); // the section under it
    act(() => FakeMap.last?.click("site-features-fill", 0));
    expect(
      fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(0);
  });
});
