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
});

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
      "GET /api/sites/addr-1907458": [SITE_BUILDING, SITE_READY],
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
    // The map loads on its own time; the panel doesn't wait for it.
    await vi.waitFor(() =>
      expect(FakeMap.last?.fitted.at(-1)).toEqual(SITE_READY.bounds),
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
