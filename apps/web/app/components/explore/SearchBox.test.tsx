import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ADDRESSES } from "@/lib/fixtures-sites";

import { SearchBox } from "./SearchBox";

function serve(body: unknown): ReturnType<typeof vi.fn> {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(body)));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  cleanup();
  vi.unstubAllGlobals();
});

async function type(text: string) {
  fireEvent.change(screen.getByRole("combobox"), { target: { value: text } });
  await act(() => vi.advanceTimersByTimeAsync(300));
}

describe("SearchBox", () => {
  it("asks once the typing pauses, and lists the addresses found", async () => {
    const fetch = serve(ADDRESSES);
    render(<SearchBox onPick={vi.fn()} />);
    await type("35 Vic");
    await type("35 Victory");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1][0]).toBe("/api/addresses?q=35%20Victory");
    const options = screen.getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining("35 Victory Street, Reefton"),
      expect.stringContaining("35 Victory Road, Laingholm, Auckland"),
    ]);
  });

  it("picks an address by click", async () => {
    serve(ADDRESSES);
    const onPick = vi.fn();
    render(<SearchBox onPick={onPick} />);
    await type("35 Victory");
    fireEvent.click(screen.getAllByRole("option")[0]);
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 1907458 }),
    );
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("picks an address with the keys", async () => {
    serve(ADDRESSES);
    const onPick = vi.fn();
    render(<SearchBox onPick={onPick} />);
    await type("35 Victory");
    const box = screen.getByRole("combobox");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1].getAttribute("aria-selected")).toBe(
      "true",
    );
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 1907459 }),
    );
  });

  it("says when nothing matches", async () => {
    serve({ addresses: [] });
    render(<SearchBox onPick={vi.fn()} />);
    await type("Nowhere Lane");
    expect(screen.getByText(/No address matches/)).toBeTruthy();
  });

  it("says why it couldn't search", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "LINZ is down" }), {
          status: 502,
        }),
      ),
    );
    render(<SearchBox onPick={vi.fn()} />);
    await type("35 Victory");
    expect(screen.getByText(/LINZ is down/)).toBeTruthy();
  });
});
