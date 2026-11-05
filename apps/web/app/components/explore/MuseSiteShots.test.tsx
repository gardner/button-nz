import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type Job, type Phase, type Site, parseJob } from "@/lib/api";
import { JOB } from "@/lib/fixtures";
import { SITE_MAP, SITE_READY } from "@/lib/fixtures-sites";
import { parseSiteMap } from "@/lib/siteMap";
import { parseSiteState } from "@/lib/sites";

import { MuseAtWork } from "./MuseAtWork";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const ID = "35-victory-street-reefton";
const SITE = parseSiteState({
  ...SITE_READY,
  aerial: {
    bbox: [1505926, 5336777, 1505970, 5336822],
    url: `/sites/${ID}/aerial.png`,
  },
}).site as Site;
const PLACE = {
  id: ID,
  address: "35 Victory Street, Reefton",
  site: SITE,
  siteMap: parseSiteMap(SITE_MAP),
};
const FLYOVER = {
  making: false,
  tiers: [
    {
      tier: "flyover",
      status: "ready",
      files: {
        video: `/sites/${ID}/relief/flyover.mp4`,
        still: `/sites/${ID}/relief/flyover.png`,
      },
    },
  ],
};
const NO_PROGRESS = {
  frame: null,
  parcels: [],
  buildings: [],
  terrain: null,
  aerial: null,
  survey: null,
};

function running(phase: Phase, attempt = 1): Job {
  return {
    ...parseJob(JOB),
    status: "running",
    acceptedAttempt: null,
    attempts: [],
    live: {
      attempt,
      phase,
      detail: "render_contours",
      view: 0,
      observations: [],
      since: null,
      newestViewAt: null,
      placement: null,
    },
  };
}

/** The API: the site's relief and build progress; the prefabs never come. */
function serve(relief: unknown = { making: false, tiers: [] }) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
    (url) => {
      const routes: Record<string, unknown> = {
        [`/api/sites/${ID}/relief`]: relief,
        [`/api/sites/${ID}/progress`]: NO_PROGRESS,
      };
      const body = routes[url];
      return body === undefined
        ? new Promise<Response>(() => {})
        : Promise.resolve(new Response(JSON.stringify(body)));
    },
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("MuseAtWork, the site's own pictures", () => {
  it("fills Blender's wait with the site's aerial, its parcels and its buildings", async () => {
    serve();
    render(<MuseAtWork job={running("rendering")} place={PLACE} />);
    const shot = await screen.findByRole("figure", { name: /Your site/ });
    expect(shot.textContent).toMatch(/LINZ aerial/);
    expect(
      shot.querySelector(`image[href="/api/sites/${ID}/aerial.png"]`),
    ).toBeTruthy();
    expect(shot.querySelectorAll('[data-layer="buildings"] path')).toHaveLength(
      2,
    );
    expect(
      screen.getByRole("heading", { name: "Blender builds and renders it" }),
    ).toBeTruthy();
  });

  it("turns to the site's fly-over, asking for nothing to be made", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(0);
    const fetch = serve(FLYOVER);
    render(<MuseAtWork job={running("thinking")} place={PLACE} />);
    await screen.findByRole("figure", { name: /Your site/ });
    act(() => vi.advanceTimersByTime(10_000));
    const video = await screen.findByLabelText("Your site, fly-over");
    expect(video.getAttribute("src")).toBe(
      `/api/sites/${ID}/relief/flyover.mp4`,
    );
    const methods = fetch.mock.calls.map(([, init]) => init?.method ?? "GET");
    expect(methods.every((m) => m === "GET")).toBe(true);
  });

  it("shows the fly-over's still to anyone who asks for less motion", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("reduce"),
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    serve(FLYOVER);
    const place = { ...PLACE, site: { ...SITE, aerial: null } };
    render(<MuseAtWork job={running("rendering")} place={place} />);
    const still = await screen.findByRole("img", { name: /fly-over/ });
    expect(still.getAttribute("src")).toBe(
      `/api/sites/${ID}/relief/flyover.png`,
    );
    expect(document.querySelector("video")).toBeNull();
  });

  it("shows the town screen's map beside Reefton's figures", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(0);
    serve();
    render(<MuseAtWork job={running("thinking")} place={PLACE} />);
    const facts = await screen.findByRole("region", { name: "Housing facts" });
    expect(facts.textContent).toMatch(/622 of 959/);
    const map = within(facts).getByRole("img", { name: /town screen's map/ });
    expect(map.getAttribute("src")).toBe("/town-screen-reefton.png");
  });

  it("leaves a lone fly-over playing as the turns go by, rather than starting it again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(0);
    serve(FLYOVER);
    const place = { ...PLACE, site: { ...SITE, aerial: null } };
    render(<MuseAtWork job={running("rendering")} place={place} />);
    const video = await screen.findByLabelText("Your site, fly-over");
    act(() => vi.advanceTimersByTime(20_000));
    expect(screen.getByLabelText("Your site, fly-over")).toBe(video);
  });

  it("shows no town map beside the national rule, on a site elsewhere", async () => {
    serve();
    const place = {
      ...PLACE,
      id: "12-main-road-westport",
      address: "12 Main Road, Westport",
    };
    render(<MuseAtWork job={running("thinking")} place={place} />);
    const facts = await screen.findByRole("region", { name: "Housing facts" });
    expect(within(facts).queryByRole("img")).toBeNull();
  });
});
