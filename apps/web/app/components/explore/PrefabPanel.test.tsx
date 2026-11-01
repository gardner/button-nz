import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
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
    onShown: vi.fn(),
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
    // Reported once the list is on the page (an effect after it renders).
    await vi.waitFor(() => expect(props.onShown).toHaveBeenCalledWith(true));
  });

  it("says a price isn't published, the area's basis, and what the supplier says of the West Coast", async () => {
    serve(PRODUCTS);
    panel();
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    expect(await screen.findByText("Price not published")).toBeTruthy();
    expect(screen.queryByText("Price on request")).toBeNull();
    expect(screen.getAllByText(/48 m² \(not stated\)/)).toHaveLength(1);
    expect(
      screen.getByText(/West Coast: West Coast is on its region list/),
    ).toBeTruthy();
  });

  it("says the list is shown only once it is, and not after it goes", async () => {
    let answer: (r: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((r) => (answer = r))),
    );
    const onShown = vi.fn();
    const { unmount } = render(
      <PrefabPanel
        jobId="abc123"
        busy={false}
        onPlace={vi.fn()}
        onHover={vi.fn()}
        onShown={onShown}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    expect(onShown).not.toHaveBeenCalledWith(true);
    answer(new Response(JSON.stringify(PRODUCTS)));
    expect(await screen.findByText("AirHome Vista")).toBeTruthy();
    await vi.waitFor(() => expect(onShown).toHaveBeenLastCalledWith(true));
    unmount();
    expect(onShown).toHaveBeenLastCalledWith(false);
  });

  it("doesn't report a list that answered after the panel went", async () => {
    let answer: (r: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((r) => (answer = r))),
    );
    const onShown = vi.fn();
    const { unmount } = render(
      <PrefabPanel
        jobId="abc123"
        busy={false}
        onPlace={vi.fn()}
        onHover={vi.fn()}
        onShown={onShown}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    unmount();
    await act(async () => answer(new Response(JSON.stringify(PRODUCTS))));
    expect(onShown).not.toHaveBeenCalledWith(true);
  });

  it("says nothing is shown when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "down" }), { status: 503 }),
        ),
      ),
    );
    const onShown = vi.fn();
    render(
      <PrefabPanel
        jobId="abc123"
        busy={false}
        onPlace={vi.fn()}
        onHover={vi.fn()}
        onShown={onShown}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Which real prefabs fit?" }),
    );
    expect(await screen.findByText(/Couldn't find prefabs/)).toBeTruthy();
    expect(onShown).not.toHaveBeenCalledWith(true);
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
