import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SITE_BUILDING, SITE_READY } from "@/lib/fixtures-sites";

import { useSite } from "./useSite";

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
  cleanup(); // an earlier test's hook would go on polling
  vi.unstubAllGlobals();
  // The hook writes ?site= to the address bar; the next test would open it.
  window.history.replaceState(null, "", "/");
});

const OTHER = {
  ...SITE_BUILDING,
  id: "addr-42",
  address: "42 Broadway, Reefton",
};

describe("useSite", () => {
  it("keeps following a build after a poll fails for a moment", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond(SITE_BUILDING, 202))
      .mockResolvedValueOnce(respond({ detail: "the API is restarting" }, 502))
      .mockResolvedValueOnce(respond(SITE_READY));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() => expect(result.current.site?.status).toBe("ready"));
    expect(result.current.problem).toBeNull();
  });

  it("keeps following a build after the connection drops for a moment", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond(SITE_BUILDING, 202))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(respond(SITE_READY));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() => expect(result.current.site?.status).toBe("ready"));
  });

  it("asks again for a linked site when the first ask fails for a moment", async () => {
    window.history.replaceState(null, "", "/?site=35-victory-street-reefton");
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond({ detail: "the API is restarting" }, 502))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(respond(SITE_READY));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    await waitFor(() => expect(result.current.site?.status).toBe("ready"));
    expect(result.current.problem).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(3);
    window.history.replaceState(null, "", "/");
  });

  it("stops asking for a linked site once the person picks their own", async () => {
    window.history.replaceState(null, "", "/?site=35-victory-street-reefton");
    const fetch = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === "POST"
          ? respond(OTHER, 202)
          : url.endsWith("/sites/35-victory-street-reefton")
            ? respond({ detail: "the API is restarting" }, 502)
            : respond(OTHER, 202),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const linked = () =>
      fetch.mock.calls.filter(([url]) =>
        String(url).endsWith("/sites/35-victory-street-reefton"),
      ).length;
    const { result } = renderHook(() => useSite(20));
    await waitFor(() => expect(result.current.problem).toContain("restarting"));
    act(() => result.current.fromAddress(42, "an address"));
    const asked = linked();
    await waitFor(() => expect(result.current.site?.id).toBe("addr-42"));
    await new Promise((r) => setTimeout(r, 100)); // several retries' worth
    expect(result.current.site?.id).toBe("addr-42");
    expect(linked()).toBe(asked);
    window.history.replaceState(null, "", "/");
  });

  it("stops asking for a linked site the API refuses for good", async () => {
    window.history.replaceState(null, "", "/?site=nowhere");
    const fetch = vi
      .fn()
      .mockResolvedValue(respond({ detail: "No site nowhere" }, 404));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    await waitFor(() => expect(result.current.problem).toContain("nowhere"));
    await new Promise((r) => setTimeout(r, 30));
    expect(fetch).toHaveBeenCalledTimes(1);
    window.history.replaceState(null, "", "/");
  });

  it("asks again for a picked address when its POST fails for a moment", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond({ detail: "the API is restarting" }, 502))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(respond(SITE_READY, 202));
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() => expect(result.current.site?.status).toBe("ready"));
    expect(result.current.problem).toBeNull();
    expect(
      fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(3);
  });

  it("doesn't let a poll of the old site replace a retried pick that answered first", async () => {
    let answerPoll: (r: Response) => void = () => {};
    let posts = 0;
    let polls = 0;
    const fetch = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts++;
        if (posts === 1) return Promise.resolve(respond(SITE_BUILDING, 202));
        if (posts === 2)
          return Promise.resolve(
            respond({ detail: "LINZ didn't answer" }, 502),
          );
        return Promise.resolve(respond(OTHER, 202));
      }
      if (url.endsWith("/35-victory-street-reefton") && ++polls >= 2)
        return new Promise<Response>((r) => (answerPoll = r)); // held
      return new Promise<Response>(() => {});
    });
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() =>
      expect(result.current.site?.id).toBe("35-victory-street-reefton"),
    );
    act(() => result.current.fromAddress(42, "an address"));
    await waitFor(() => expect(result.current.site?.id).toBe("addr-42"));
    await act(async () => answerPoll(respond(SITE_BUILDING)));
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.site?.id).toBe("addr-42");
  });

  it("asks only once when the daily cap refuses a pick, and says why", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        respond({ detail: "Today's site builds are used." }, 429),
      );
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() => expect(result.current.problem).toContain("used"));
    await new Promise((r) => setTimeout(r, 40));
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("stops following when the site is gone for good, and says why", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond(SITE_BUILDING, 202))
      .mockResolvedValue(
        respond({ detail: "no site 35-victory-street-reefton" }, 404),
      );
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() => expect(result.current.problem).toContain("no site"));
    const calls = fetch.mock.calls.length;
    await new Promise((r) => setTimeout(r, 40));
    expect(fetch.mock.calls.length).toBe(calls);
  });

  it("keeps following the site on show when a new pick fails, and keeps saying why", async () => {
    let failed = false; // the second pick has been refused
    let pollsSince = 0; // polls of the first site since then
    const fetch = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(init.body).includes("42")) {
        failed = true;
        return Promise.resolve(respond({ detail: "LINZ didn't answer" }, 502));
      }
      if (init?.method === "POST")
        return Promise.resolve(respond(SITE_BUILDING, 202));
      if (failed) pollsSince += 1;
      const ready = { ...SITE_READY, id: "35-victory-street-reefton" };
      // Still building for two polls after the refusal, then ready.
      return Promise.resolve(respond(pollsSince < 3 ? SITE_BUILDING : ready));
    });
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() =>
      expect(result.current.site?.id).toBe("35-victory-street-reefton"),
    );
    act(() => result.current.fromAddress(42, "an address"));
    await waitFor(() => expect(result.current.site?.status).toBe("ready"));
    expect(pollsSince).toBeGreaterThanOrEqual(3); // polls answered after it
    expect(result.current.problem).toContain("LINZ"); // and didn't clear it
  });

  it("forgets the last pick's failure as soon as a new pick starts", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(respond({ detail: "LINZ didn't answer" }, 502))
      .mockReturnValueOnce(new Promise<Response>(() => {})); // the next, still on its way
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() => expect(result.current.problem).toContain("LINZ"));
    act(() => result.current.fromAddress(42, "an address"));
    expect(result.current.problem).toBeNull();
  });

  it("keeps a newer pick when an older site's poll answers after it", async () => {
    let answerPick: (r: Response) => void = () => {};
    const fetch = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(init.body).includes("42"))
        return new Promise<Response>((resolve) => (answerPick = resolve));
      if (init?.method === "POST")
        return Promise.resolve(respond(SITE_BUILDING, 202));
      // Each site's poll answers with that site, both still building.
      return Promise.resolve(
        respond(url.endsWith("/addr-42") ? OTHER : SITE_BUILDING),
      );
    });
    vi.stubGlobal("fetch", fetch);
    const { result } = renderHook(() => useSite(5));
    act(() => result.current.fromAddress(1907458, "an address"));
    await waitFor(() =>
      expect(result.current.site?.id).toBe("35-victory-street-reefton"),
    );
    act(() => result.current.fromAddress(42, "an address"));
    await new Promise((r) => setTimeout(r, 30)); // several polls of the first site
    await act(async () => answerPick(respond(OTHER, 202)));
    await waitFor(() => expect(result.current.site?.id).toBe("addr-42"));
    await new Promise((r) => setTimeout(r, 30));
    expect(result.current.site?.id).toBe("addr-42");
  });
});
