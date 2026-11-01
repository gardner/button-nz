import { describe, expect, it } from "vitest";

import { creditOf } from "./credit";

const LINZ = "Toitū Te Whenua Land Information New Zealand";

describe("creditOf", () => {
  it("credits each provider once, with the works of theirs used and the licence", () => {
    const credit = creditOf([
      {
        key: "dem",
        title: "West Coast LiDAR 1m DEM",
        licence: "CC-BY-4.0",
        attribution: `${LINZ}, West Coast Regional Council`,
        capture: null,
      },
      {
        key: "dsm",
        title: "West Coast LiDAR 1m DSM",
        licence: "CC-BY-4.0",
        attribution: `${LINZ}, West Coast Regional Council`,
        capture: null,
      },
      {
        key: "aerial",
        title: "Buller Urban Aerial Photos",
        licence: "CC-BY-4.0",
        attribution: `${LINZ}, Buller District Council`,
        capture: null,
      },
    ]);
    expect(credit).toBe(
      `This site: West Coast LiDAR 1m DEM, West Coast LiDAR 1m DSM: ${LINZ}, West Coast Regional Council, CC BY 4.0 · ` +
        `Buller Urban Aerial Photos: ${LINZ}, Buller District Council, CC BY 4.0`,
    );
  });

  it("says a licence as its source states it, when it isn't a CC one", () => {
    const credit = creditOf([
      {
        key: "parcels",
        title: "BDC parcels",
        licence: "not stated",
        attribution: "Buller District Council",
        capture: null,
      },
    ]);
    expect(credit).toBe(
      "This site: BDC parcels: Buller District Council, licence not stated",
    );
  });

  it("escapes the sources' words: the map's credit line is HTML", () => {
    const credit = creditOf([
      {
        key: "dem",
        title: "A & B <C>",
        licence: "CC-BY-4.0",
        attribution: `<img src=x onerror="alert(1)">`,
        capture: null,
      },
    ]);
    expect(credit).toBe(
      "This site: A &amp; B &lt;C&gt;: &lt;img src=x onerror=&quot;alert(1)&quot;&gt;, CC BY 4.0",
    );
  });

  it("credits nothing for a site with no sources", () => {
    expect(creditOf([])).toBeUndefined();
  });
});
