import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PRODUCTS } from "@/lib/fixtures";

import { PrefabPanel } from "./PrefabPanel";

function serve(body: unknown): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(body))),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function panel(overrides: Partial<Parameters<typeof PrefabPanel>[0]> = {}) {
  const props = {
    jobId: "abc123",
    busy: false,
    onPlace: vi.fn(),
    onHover: vi.fn(),
    onAsked: vi.fn(),
    ...overrides,
  };
  render(<PrefabPanel {...props} />);
  return props;
}

describe("PrefabPanel", () => {
  it("asks which real prefabs fit, and shows each with its price and size", async () => {
    const fetch = serve(PRODUCTS);
    const props = panel();
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    expect(fetch.mock.calls[0][0]).toBe("/api/designs/abc123/products");
    expect(await screen.findByText("AirHome Vista")).toBeTruthy();
    expect(screen.getByText(/12.2 × 4 m · 48 m²/)).toBeTruthy();
    expect(screen.getByText("$190,000")).toBeTruthy();
    expect(props.onAsked).toHaveBeenCalled();
  });

  it("shows where a product would stand while it is pointed at", async () => {
    serve(PRODUCTS);
    const props = panel();
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    const card = (await screen.findByText("AirHome Vista")).closest("article");
    fireEvent.mouseEnter(card as Element);
    expect(props.onHover).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: "airhome-vista" }),
    );
    fireEvent.mouseLeave(card as Element);
    expect(props.onHover).toHaveBeenLastCalledWith(null);
  });

  it("places a product that can be placed", async () => {
    serve(PRODUCTS);
    const props = panel();
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Place the AirHome Vista on the site",
      }),
    );
    expect(props.onPlace).toHaveBeenCalledWith(
      expect.objectContaining({ id: "airhome-vista" }),
    );
  });

  it("names what it couldn't check, and what comes next", async () => {
    serve(PRODUCTS);
    panel();
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    expect(await screen.findByText(/Not checked/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Next steps" })).toBeTruthy();
  });
});
