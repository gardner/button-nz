import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PRODUCTS } from "@/lib/fixtures";

import { ProductsPanel } from "./ProductsPanel";

function serve(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function ask(): Promise<void> {
  await userEvent.click(
    screen.getByRole("button", { name: "Which real prefabs fit?" }),
  );
}

describe("ProductsPanel", () => {
  it("asks only when the owner wants to know", async () => {
    const fetch = serve(PRODUCTS);
    render(<ProductsPanel jobId="abc123" />);
    expect(fetch).not.toHaveBeenCalled();
    await ask();
    expect(fetch).toHaveBeenCalledWith("/api/designs/abc123/products", undefined);
  });

  it("lists the products that fit, with their published price and source", async () => {
    serve(PRODUCTS);
    render(<ProductsPanel jobId="abc123" />);
    await ask();
    const vista = await screen.findByRole("link", { name: "AirHome Vista" });
    expect((vista as HTMLAnchorElement).href).toBe(
      "https://www.airhome.co.nz/airhome-vista/",
    );
    expect(screen.getByText(/12\.2 × 4 m · 48 m² · 2 bed, 1 bath/)).toBeTruthy();
    expect(screen.getByText(/\$190,000 \(incl GST; construction only\)/)).toBeTruthy();
    expect(screen.getByText(/Excludes: decking, landscaping/)).toBeTruthy();
    // a price the supplier doesn't publish is said so, never estimated
    expect(
      screen.getByText(/Price not published \(price on application; prices incl GST\)/),
    ).toBeTruthy();
  });

  it("names the products it could not check, and what fitting means", async () => {
    serve(PRODUCTS);
    render(<ProductsPanel jobId="abc123" />);
    await ask();
    expect(
      await screen.findByText(/Not checked \(dimensions not labelled\): Keith Hay Homes Nook 60/),
    ).toBeTruthy();
    expect(screen.getByText(/lies inside the accepted design's walls/)).toBeTruthy();
  });

  it("says when nothing in the catalogue fits", async () => {
    serve({ ...PRODUCTS, fits: [] });
    render(<ProductsPanel jobId="abc123" />);
    await ask();
    expect(
      await screen.findByText(/No catalogue product fits inside these 65 m² walls/),
    ).toBeTruthy();
  });

  it("shows why the products couldn't be found", async () => {
    serve({ detail: "design abc123 has no accepted attempt" }, 409);
    render(<ProductsPanel jobId="abc123" />);
    await ask();
    expect(
      await screen.findByText(/Could not find products: design abc123 has no accepted attempt/),
    ).toBeTruthy();
  });
});

describe("ProductsPanel next steps", () => {
  it("points to the council and the research on local firms", async () => {
    serve(PRODUCTS);
    render(<ProductsPanel jobId="abc123" />);
    await ask();
    const council = await screen.findByRole("link", { name: "Buller District Council" });
    expect((council as HTMLAnchorElement).href).toContain("bullerdc.govt.nz");
    const firms = screen.getByRole("link", { name: /Local firms/ });
    expect((firms as HTMLAnchorElement).href).toContain("docs/suppliers.md");
  });
});
