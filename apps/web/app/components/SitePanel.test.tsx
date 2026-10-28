import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Site } from "@/lib/api";
import { parseSurvey } from "@/lib/features";
import { SURVEY } from "@/lib/fixtures";

import { SitePanel } from "./SitePanel";

const SITE: Site = {
  name: "35 Victory Street, Reefton",
  title: "354613",
  valuationNumber: "1905027200",
  address: [1005, 2010],
  extent: [1000, 2000, 1020, 2020],
  parcels: [
    {
      id: 1,
      appellation: "Section 700 Town of Reefton",
      ring: [
        [1000, 2000],
        [1010, 2000],
        [1010, 2020],
        [1000, 2020],
        [1000, 2000],
      ],
    },
    {
      id: 2,
      appellation: "Section 701 Town of Reefton",
      ring: [
        [1010, 2000],
        [1020, 2000],
        [1020, 2020],
        [1010, 2020],
        [1010, 2000],
      ],
    },
  ],
  sources: [
    {
      key: "dem",
      title: "West Coast LiDAR 1m DEM",
      licence: "CC-BY-4.0",
      attribution: "Toitū Te Whenua LINZ",
      capture: { start: "2020-05-15T12:00:00Z", end: "2024-07-10T12:00:00Z" },
    },
  ],
  openItems: ["Confirm the boundary pegs."],
  aerial: null,
};

afterEach(cleanup);

describe("SitePanel", () => {
  it("shows the title, the parcels on a plan, the sources and what is still open", () => {
    const { container } = render(<SitePanel site={SITE} />);
    expect(screen.getByText("35 Victory Street, Reefton")).toBeTruthy();
    expect(screen.getByText(/Record of title 354613/)).toBeTruthy();
    expect(container.querySelectorAll("svg path.parcel")).toHaveLength(2);
    expect(screen.getByText("Section 701 Town of Reefton")).toBeTruthy();
    expect(screen.getByText(/CC-BY-4.0/)).toBeTruthy();
    expect(screen.getByText(/Toitū Te Whenua LINZ/)).toBeTruthy();
    expect(screen.getByText(/2020-05-15 to 2024-07-10/)).toBeTruthy();
    expect(screen.getByText("Confirm the boundary pegs.")).toBeTruthy();
  });

  it("draws the surveyed features on the plan, undecided ones dashed", () => {
    const { features } = parseSurvey(SURVEY);
    const { container } = render(<SitePanel site={SITE} features={features} />);
    const drawn = [...container.querySelectorAll("svg path.feature")];
    expect(drawn.map((p) => p.getAttribute("data-decision"))).toEqual([
      "building",
      "undecided",
      "undecided",
    ]);
    const [shed, tree] = drawn;
    expect(shed.getAttribute("stroke-dasharray")).toBeNull();
    expect(tree.getAttribute("stroke-dasharray")).not.toBeNull();
    expect(tree.getAttribute("d")?.match(/M/g)).toHaveLength(2); // two pieces
    expect(shed.textContent).toBe("#1 shed: existing building");
    expect(screen.getByText("Not decided yet")).toBeTruthy();
  });

  it("lays the aerial photo under the plan, true to scale", () => {
    const aerial = {
      bbox: [990, 1990, 1030, 2030] as [number, number, number, number],
      url: "/api/site/aerial.png",
    };
    const { container } = render(<SitePanel site={{ ...SITE, aerial }} />);
    const image = container.querySelector("svg image");
    expect(image?.getAttribute("href")).toBe("/api/site/aerial.png");
    // The plan's origin is the extent's north-west corner less the margin.
    const [x, y] = [
      Number(image?.getAttribute("x")),
      Number(image?.getAttribute("y")),
    ];
    const [, , width] = (
      container.querySelector("svg")?.getAttribute("viewBox") ?? ""
    )
      .split(" ")
      .map(Number);
    const margin = (width - 20) / 2;
    expect([x, y]).toEqual([margin - 10, margin - 10]); // 10 m west and north of the extent
    expect(image?.getAttribute("width")).toBe("40");
    expect(image?.getAttribute("height")).toBe("40");
    expect(container.querySelector("svg")?.firstElementChild?.tagName).toBe(
      "image",
    );
  });

  it("numbers the features on the plan as in the list", () => {
    const { features } = parseSurvey(SURVEY);
    const { container } = render(<SitePanel site={SITE} features={features} />);
    const labels = [...container.querySelectorAll("svg text.feature-label")];
    expect(labels.map((t) => t.textContent)).toEqual(features.map((f) => f.id));
  });

  it("has no features or legend without a survey", () => {
    const { container } = render(<SitePanel site={SITE} />);
    expect(container.querySelector("svg path.feature")).toBeNull();
    expect(screen.queryByText("Not decided yet")).toBeNull();
  });
});
