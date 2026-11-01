import { afterEach, describe, expect, it, vi } from "vitest";

import { framing } from "./BaseMap";

/** A window `width` × `height`, with the panel over the map at `box`. */
function screenWith(width: number, height: number, box: DOMRect) {
  Object.defineProperty(window, "innerWidth", {
    value: width,
    configurable: true,
  });
  Object.defineProperty(window, "innerHeight", {
    value: height,
    configurable: true,
  });
  const panel = document.createElement("aside");
  panel.setAttribute("data-map-panel", "");
  panel.getBoundingClientRect = () => box;
  document.body.appendChild(panel);
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("framing", () => {
  it("keeps the hero in the panel below 1280 px, and frames beside the panel", () => {
    screenWith(1024, 768, new DOMRect(16, 80, 440, 672)); // full height
    expect(framing(440)).toMatchObject({ left: 480, right: 24 });
  });

  it("leaves room for the hero on the right from 1280 px", () => {
    screenWith(1280, 800, new DOMRect(16, 80, 440, 704));
    expect(framing(440)).toMatchObject({ left: 480, right: 440 });
  });
});
