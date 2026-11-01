import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ADDRESSES,
  SITE_BUILDING,
  SITE_READY,
  TOWN,
} from "@/lib/fixtures-sites";

import { FakeMap } from "../map/fakeMap";
import { ATTRIBUTION, REEFTON } from "../map/BaseMap";
import { Explore } from "./Explore";

vi.mock("maplibre-gl", async () => ({
  Map: (await import("../map/fakeMap")).FakeMap,
  setWorkerUrl: () => {},
}));

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/** Answer each request by its path, from `routes`; anything else never answers. */
function serve(routes: Record<string, unknown[]>): ReturnType<typeof vi.fn> {
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url.split("?")[0]}`;
    const queue = routes[key];
    if (!queue?.length) return new Promise<Response>(() => {});
    return Promise.resolve(
      respond(queue.length > 1 ? queue.shift() : queue[0]),
    );
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  FakeMap.last = null;
  window.history.replaceState(null, "", "/"); // a site picked writes ?site=
});

/** The options of each fit to the ready site, oldest first. */
function siteFits(): unknown[] {
  const map = FakeMap.last;
  if (!map) return [];
  return map.fitOptions.filter(
    (_, i) =>
      JSON.stringify(map.fitted[i]) === JSON.stringify(SITE_READY.bounds),
  );
}

describe("Explore", () => {
  it("shows the town's sections, coloured, and its headline counted from them", async () => {
    serve({ "GET /api/town/reefton": [TOWN] });
    render(<Explore pollMs={5} />);
    expect(
      await screen.findByText(/sections have room for a real prefab/),
    ).toBeTruthy();
    expect(screen.getByText(/of Reefton/).textContent).toContain(
      "2 of Reefton's 3 sections",
    );
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("town-fill")).toBe(true),
    );
    expect(
      screen.getByRole("listitem", { current: "step" }).textContent,
    ).toContain("Find");
  });

  it("says how many screened sections aren't on the map, and doesn't call the rest the town's total", async () => {
    serve({
      "GET /api/town/reefton": [
        {
          ...TOWN,
          missing: { ids: [7, 8], reason: "not in LINZ's NZ Primary Parcels" },
        },
      ],
    });
    render(<Explore pollMs={5} />);
    expect(
      (await screen.findByText(/have room for a real prefab/)).textContent,
    ).toContain("2 of the 3 mapped sections in Reefton");
    expect(
      screen.getByText(/2 more screened sections aren't on the map/)
        .textContent,
    ).toContain("not in LINZ's NZ Primary Parcels");
  });

  it("frames the site clear of the panel: beside it when there's room, under it on a phone", async () => {
    const screen_ = (width: number, height: number) => {
      Object.defineProperty(window, "innerWidth", {
        value: width,
        configurable: true,
      });
      Object.defineProperty(window, "innerHeight", {
        value: height,
        configurable: true,
      });
    };
    let box = new DOMRect();
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
      function (this: HTMLElement) {
        return this.dataset.mapPanel === undefined ? new DOMRect() : box;
      },
    );
    const panel = (width: number, height: number) =>
      (box = new DOMRect(16, 80, width, height));
    const fly = async () => {
      serve({
        "GET /api/town/reefton": [TOWN],
        [`GET /api/sites/${SITE_READY.id}`]: [SITE_READY],
      });
      window.history.replaceState(null, "", `/?site=${SITE_READY.id}`);
      render(<Explore pollMs={5} />);
      await vi.waitFor(() => expect(siteFits()).toHaveLength(1));
      const options = siteFits()[0] as { padding: Record<string, number> };
      cleanup();
      FakeMap.last = null; // the next page's map is a new one
      window.history.replaceState(null, "", "/");
      return options.padding;
    };
    screen_(1440, 900);
    panel(440, 300);
    expect(await fly()).toMatchObject({ left: 16 + 440 + 24 });
    screen_(390, 844);
    panel(358, 370);
    expect(await fly()).toMatchObject({ top: 80 + 370 + 24, left: 24 });
    screen_(844, 390); // the phone turned: more room beside the panel
    panel(440, 294);
    expect(await fly()).toMatchObject({ left: 16 + 440 + 24 });
    screen_(320, 480); // a small phone, the panel full: no gutter to frame in
    panel(288, 384);
    expect(await fly()).toMatchObject({ top: 480 * 0.6, left: 24 });
    vi.restoreAllMocks();
  });

  it("frames the town again once its headline is in the panel", async () => {
    serve({ "GET /api/town/reefton": [TOWN] });
    render(<Explore pollMs={5} />);
    expect(
      await screen.findByText(/sections have room for a real prefab/),
    ).toBeTruthy();
    // Once as the map opens, again with the headline in the panel.
    await vi.waitFor(() =>
      expect(FakeMap.last?.fitted).toEqual([REEFTON, REEFTON]),
    );
  });

  it("frames the site again when the map changes shape", async () => {
    serve({
      "GET /api/town/reefton": [TOWN],
      [`GET /api/sites/${SITE_READY.id}`]: [SITE_READY],
    });
    window.history.replaceState(null, "", `/?site=${SITE_READY.id}`);
    render(<Explore pollMs={5} />);
    await vi.waitFor(() => expect(siteFits()).toHaveLength(1));
    act(() => FakeMap.last?.fire("resize")); // the map has taken its new size
    expect(siteFits()).toHaveLength(2);
    expect(siteFits()[1]).toMatchObject({ duration: 0 });
  });

  it("stands the town's buildings up in 3D, and lays them down in 2D", async () => {
    serve({ "GET /api/town/reefton": [TOWN] });
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("town-fill")).toBe(true),
    );
    const map = FakeMap.last!;
    expect(map.layers.has("town-buildings-extrusion")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "3D" }));
    expect(map.layers.get("town-buildings-extrusion")).toMatchObject({
      type: "fill-extrusion",
      paint: {
        "fill-extrusion-base": 0,
        // half the measured height: context, not the design (CONTEXT_SCALE)
        "fill-extrusion-height": [
          "*",
          ["-", ["get", "heightM"], ["get", "baseM"]],
          0.5,
        ],
      },
    });
    // Only the buildings the LiDAR measured stand.
    const standing = map.sources.get("town-buildings")?.data as {
      features: unknown[];
    };
    expect(standing.features).toHaveLength(1);
    await vi.waitFor(() => expect(map.pitch).toBe(60));
    // Closer in, for buildings a few metres tall to show.
    await new Promise((r) => setTimeout(r, 20));
    expect(map.zoom).toBeGreaterThanOrEqual(15.8);
    expect(
      screen.getByRole("button", { name: "3D" }).getAttribute("aria-pressed"),
    ).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "2D" }));
    expect(map.layers.has("town-buildings-extrusion")).toBe(false);
    await vi.waitFor(() => expect(map.pitch).toBe(0));
  });

  it("tilts the town when 3D is chosen before the town has loaded", async () => {
    let answer: (r: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((r) => (answer = r))),
    );
    render(<Explore pollMs={5} />);
    await vi.waitFor(() => expect(FakeMap.last).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "3D" }));
    answer(respond(TOWN));
    expect(
      await screen.findByText(/sections have room for a real prefab/),
    ).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    expect(FakeMap.last?.pitch).toBe(60);
  });

  it("asks for addresses near where the map looks first", async () => {
    const fetch = serve({
      "GET /api/town/reefton": [TOWN],
      "GET /api/addresses": [ADDRESSES],
    });
    render(<Explore pollMs={5} />);
    await vi.waitFor(() => expect(FakeMap.last).not.toBeNull());
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    await screen.findByRole("option", { name: /35 Victory Street, Reefton/ });
    const asked = fetch.mock.calls
      .map((c) => String(c[0]))
      .find((u) => u.startsWith("/api/addresses"));
    expect(asked).toBe(
      "/api/addresses?q=35%20Victory&near=171.8622%2C-42.1153",
    );
  });

  it("goes back to the town while a newly picked site builds", async () => {
    serve({
      "GET /api/town/reefton": [TOWN],
      [`GET /api/sites/${SITE_READY.id}`]: [SITE_READY],
      "GET /api/addresses": [ADDRESSES],
      "POST /api/sites": [{ ...SITE_BUILDING, id: "addr-42" }],
    });
    window.history.replaceState(null, "", `/?site=${SITE_READY.id}`);
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.landed.at(-1)).toEqual(SITE_READY.bounds),
    );
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    fireEvent.click(
      await screen.findByRole("option", { name: /35 Victory Road, Laingholm/ }),
    );
    await vi.waitFor(() =>
      expect(FakeMap.last?.landed.at(-1)).toEqual(REEFTON),
    );
  });

  it("keeps the town's buildings standing in 3D while a picked site builds", async () => {
    serve({
      "GET /api/town/reefton": [TOWN],
      "GET /api/addresses": [ADDRESSES],
      "POST /api/sites": [{ ...SITE_BUILDING, id: "addr-42" }],
    });
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("town-fill")).toBe(true),
    );
    fireEvent.click(screen.getByRole("button", { name: "3D" }));
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    fireEvent.click(
      await screen.findByRole("option", { name: /35 Victory Road, Laingholm/ }),
    );
    expect(await screen.findByRole("status")).toBeTruthy(); // building
    expect(FakeMap.last?.layers.has("town-buildings-extrusion")).toBe(true);
  });

  it("comes back to the town's own 3D zoom from a close-up while a new site builds", async () => {
    serve({
      "GET /api/town/reefton": [TOWN],
      [`GET /api/sites/${SITE_READY.id}`]: [SITE_READY],
      "GET /api/addresses": [ADDRESSES],
      "POST /api/sites": [{ ...SITE_BUILDING, id: "addr-42" }],
    });
    window.history.replaceState(null, "", `/?site=${SITE_READY.id}`);
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.landed.at(-1)).toEqual(SITE_READY.bounds),
    );
    fireEvent.click(screen.getByRole("button", { name: "3D" }));
    const map = FakeMap.last!;
    await vi.waitFor(() => expect(map.pitch).toBe(60));
    map.zoom = 19.5; // a close-up of the site
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    fireEvent.click(
      await screen.findByRole("option", { name: /35 Victory Road, Laingholm/ }),
    );
    await vi.waitFor(() => expect(map.zoom).toBe(15.8));
  });

  it("asks again for the town when it fails for a moment, but not when refused", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond({ detail: "the API is restarting" }, 502))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(respond(TOWN));
    vi.stubGlobal("fetch", fetch);
    render(<Explore pollMs={5} />);
    expect(
      await screen.findByText(/sections have room for a real prefab/),
    ).toBeTruthy();
    expect(screen.queryByText(/town map couldn't load/)).toBeNull();
    cleanup();
    const refused = vi
      .fn()
      .mockResolvedValue(
        respond({ detail: "no town screen for reefton" }, 404),
      );
    vi.stubGlobal("fetch", refused);
    render(<Explore pollMs={5} />);
    expect(await screen.findByText(/no town screen/)).toBeTruthy();
    await new Promise((r) => setTimeout(r, 30));
    expect(refused).toHaveBeenCalledTimes(1);
  });

  it("builds the site of a found address, step by step, and flies there", async () => {
    const fetch = serve({
      "GET /api/town/reefton": [TOWN],
      "GET /api/addresses": [ADDRESSES],
      "POST /api/sites": [SITE_BUILDING],
      "GET /api/sites/35-victory-street-reefton": [SITE_BUILDING, SITE_READY],
    });
    render(<Explore pollMs={5} />);
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    fireEvent.click(
      await screen.findByRole("option", { name: /35 Victory Street, Reefton/ }),
    );
    expect((await screen.findByRole("status")).textContent).toContain(
      "Reading the LiDAR",
    );
    expect(await screen.findByText("Your site")).toBeTruthy();
    // The map loads on its own time; the panel doesn't wait for it. The fly
    // to the site lands: nothing stops it on the way.
    await vi.waitFor(() =>
      expect(FakeMap.last?.landed.at(-1)).toEqual(SITE_READY.bounds),
    );
    expect(window.location.search).toBe("?site=35-victory-street-reefton");
    expect(
      screen.getByRole("listitem", { current: "step" }).textContent,
    ).toContain("Survey");
    const posted = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(posted?.[1]?.body))).toEqual({
      address_id: 1907458,
    });
  });

  it("doesn't build a site from a section clicked on the town map", async () => {
    // POST /sites takes an address only (#88): a section isn't a link yet.
    const fetch = serve({ "GET /api/town/reefton": [TOWN] });
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("town-fill")).toBe(true),
    );
    act(() => FakeMap.last?.click("town-fill", 1));
    expect(
      fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(0);
    expect(screen.queryByText(/Tap one/)).toBeNull();
  });

  it("credits Reefton's aerial photos while the town is on show, until a ready site credits its own", async () => {
    serve({
      "GET /api/town/reefton": [TOWN],
      "GET /api/addresses": [ADDRESSES],
      "POST /api/sites": [SITE_BUILDING],
      "GET /api/sites/35-victory-street-reefton": [SITE_BUILDING, SITE_READY],
    });
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.sources.get("town-credit")?.attribution).toContain(
        "Buller District Council",
      ),
    );
    expect(ATTRIBUTION).not.toContain("Reefton");
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "35 Victory" },
    });
    fireEvent.click(
      await screen.findByRole("option", { name: /35 Victory Street, Reefton/ }),
    );
    // While it builds, the map still shows the town's photos.
    expect((await screen.findByRole("status")).textContent).toContain(
      "Reading the LiDAR",
    );
    expect(FakeMap.last?.sources.has("town-credit")).toBe(true);
    expect(await screen.findByText("Your site")).toBeTruthy();
    // A site elsewhere (Petone) isn't Reefton's: the site credits its own.
    expect(FakeMap.last?.sources.has("town-credit")).toBe(false);
  });

  it("credits Reefton's photos before the town's sections have come", async () => {
    serve({}); // the town never answers
    render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.sources.has("town-credit")).toBe(true),
    );
  });

  it("leaves cleanly, after the map itself is gone", async () => {
    serve({ "GET /api/town/reefton": [TOWN] });
    const { unmount } = render(<Explore pollMs={5} />);
    await vi.waitFor(() =>
      expect(FakeMap.last?.layers.has("town-fill")).toBe(true),
    );
    expect(() => unmount()).not.toThrow();
  });

  it("reopens the site in the link", async () => {
    window.history.replaceState(null, "", "/?site=35-victory-street-reefton");
    serve({
      "GET /api/town/reefton": [TOWN],
      "GET /api/sites/35-victory-street-reefton": [SITE_READY],
    });
    render(<Explore pollMs={5} />);
    expect(await screen.findByText("Your site")).toBeTruthy();
  });
});
