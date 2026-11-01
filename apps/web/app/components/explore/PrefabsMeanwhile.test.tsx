import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PRODUCTS } from "@/lib/fixtures";

import { PrefabsMeanwhile } from "./PrefabsMeanwhile";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PrefabsMeanwhile", () => {
  it("lists the real catalogue to browse, with sizes, prices and the supplier's page", async () => {
    const catalogue = [...PRODUCTS.fits, ...PRODUCTS.unchecked];
    const fetch = vi.fn((url: string) =>
      Promise.resolve(new Response(JSON.stringify(url && catalogue))),
    );
    vi.stubGlobal("fetch", fetch);
    render(<PrefabsMeanwhile />);
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(catalogue.length);
    expect(fetch.mock.calls[0][0]).toBe("/api/products");
    const first = catalogue[0];
    expect(items[0].textContent).toContain(first.model);
    expect(items[0].textContent).toContain(
      `${first.length_m} × ${first.width_m} m`,
    );
    const link = screen.getAllByRole("link")[0];
    expect(link.getAttribute("href")).toBe(first.url);
  });

  it("says when the catalogue couldn't load, rather than showing nothing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 503 }))),
    );
    render(<PrefabsMeanwhile />);
    expect(await screen.findByText(/couldn.t load the prefabs/i)).toBeTruthy();
  });
});
