import { describe, expect, it } from "vitest";

import { ATTRIBUTION, collapseCredits } from "./BaseMap";

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

describe("ATTRIBUTION", () => {
  it("credits the basemap, the sections and the heights each on its own line", () => {
    const box = document.createElement("div");
    box.innerHTML = ATTRIBUTION;
    expect([...box.querySelectorAll("p")].map((p) => p.textContent)).toEqual([
      "Aerial: Toitū Te Whenua LINZ basemap, CC BY 4.0",
      "Sections: LINZ NZ Primary Parcels, CC BY 4.0",
      "Heights: LINZ 1 m LiDAR, CC BY 4.0",
    ]);
  });
});
