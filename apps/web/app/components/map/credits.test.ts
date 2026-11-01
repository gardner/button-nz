import { describe, expect, it } from "vitest";

import { collapseCredits } from "./BaseMap";

describe("collapseCredits", () => {
  it("folds the credit line behind its ⓘ button, keeping every credit", () => {
    const map = document.createElement("div");
    map.innerHTML =
      '<details class="maplibregl-ctrl-attrib maplibregl-compact maplibregl-compact-show" open>' +
      '<summary class="maplibregl-ctrl-attrib-button"></summary>' +
      '<div class="maplibregl-ctrl-attrib-inner">LINZ, CC BY 4.0</div></details>';
    collapseCredits(map);
    const credits = map.querySelector(".maplibregl-ctrl-attrib");
    expect(credits?.classList.contains("maplibregl-compact-show")).toBe(false);
    expect(credits?.textContent).toContain("LINZ, CC BY 4.0");
  });
});
