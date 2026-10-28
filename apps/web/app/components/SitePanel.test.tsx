import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Site } from "@/lib/api";

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
});
