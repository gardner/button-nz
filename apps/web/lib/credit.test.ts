import { describe, expect, it } from "vitest";

import { creditLines, creditOf } from "./credit";

const LINZ = "Toitū Te Whenua Land Information New Zealand";

/** The lines a credit shows, as the map shows them. */
function linesOf(credit: string | undefined): string[] {
  const box = document.createElement("div");
  box.innerHTML = credit ?? "";
  return [...box.querySelectorAll("p")].map((line) => line.textContent ?? "");
}

/** Words of a credit outside its element: the map hides those (they are
 * MapLibre's separators between sources), so a credit may have none. */
function bareText(credit: string | undefined): string {
  const box = document.createElement("div");
  box.innerHTML = credit ?? "";
  return [...box.childNodes]
    .filter((node) => node.nodeType === Node.TEXT_NODE)
    .map((node) => node.textContent)
    .join("")
    .trim();
}

describe("creditLines", () => {
  it("puts each credit on its own line, all inside one element", () => {
    const credit = creditLines(["Aerial: LINZ, CC BY 4.0", "Heights: LINZ"]);
    expect(linesOf(credit)).toEqual([
      "Aerial: LINZ, CC BY 4.0",
      "Heights: LINZ",
    ]);
    expect(bareText(credit)).toBe("");
  });
});

describe("creditOf", () => {
  it("credits each provider once, on its own line, with the works of theirs used and the licence", () => {
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
    expect(linesOf(credit)).toEqual([
      "This site:",
      `West Coast LiDAR 1m DEM, West Coast LiDAR 1m DSM: ${LINZ}, West Coast Regional Council, CC BY 4.0`,
      `Buller Urban Aerial Photos: ${LINZ}, Buller District Council, CC BY 4.0`,
    ]);
    expect(bareText(credit)).toBe("");
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
    expect(linesOf(credit)).toEqual([
      "This site:",
      "BDC parcels: Buller District Council, licence not stated",
    ]);
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
    expect(credit).toContain(
      "<p>A &amp; B &lt;C&gt;: &lt;img src=x onerror=&quot;alert(1)&quot;&gt;, CC BY 4.0</p>",
    );
  });

  it("credits nothing for a site with no sources", () => {
    expect(creditOf([])).toBeUndefined();
  });
});
