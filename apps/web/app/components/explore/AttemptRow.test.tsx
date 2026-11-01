import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { type Attempt, parseJob } from "@/lib/api";
import { JOB } from "@/lib/fixtures";
import { CHECKS } from "@/lib/fixtures-sites";

import { AttemptRow, checkLabel } from "./AttemptRow";

afterEach(cleanup);

function attempt(checks: unknown): Attempt {
  const raw = {
    ...JOB,
    attempts: [
      { ...JOB.attempts[0], ...(checks === undefined ? {} : { checks }) },
    ],
  };
  return parseJob(raw).attempts[0];
}

describe("AttemptRow", () => {
  it("shows each check as a badge, pass, fail or unknown", () => {
    render(<AttemptRow attempt={attempt(CHECKS)} />);
    const badges = within(screen.getByRole("list", { name: "Checks" }))
      .getAllByRole("listitem")
      .map((b) => b.textContent);
    expect(badges).toEqual([
      "✓ 2 m from the boundary",
      "? 2 m from buildings",
      "✗ 70 m² or less",
    ]);
  });

  it("doesn't call an attempt with unknown checks a pass", () => {
    const unknown = {
      ...attempt(CHECKS.slice(0, 2)),
      status: "unknown" as const,
    };
    render(<AttemptRow attempt={unknown} />);
    expect(screen.getByText("No failures; some checks unknown")).toBeTruthy();
    expect(screen.queryByText(/Passed/)).toBeNull();
  });

  it("opens to each check's measurement and the rule it comes from", () => {
    render(<AttemptRow attempt={attempt(CHECKS)} />);
    expect(screen.queryByText(/72.0 m²: over 70/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Details/ }));
    expect(screen.getByText(/72.0 m²: over 70/)).toBeTruthy();
    expect(screen.getAllByText(/Building Act 2004, Schedule 1A/).length).toBe(
      3,
    );
  });

  it("shows the evaluator's words when the API sends no checks", () => {
    render(<AttemptRow attempt={attempt(undefined)} />);
    expect(screen.queryByRole("list", { name: "Checks" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Details/ }));
    expect(screen.getByText(/0.50 m from the boundary/)).toBeTruthy();
  });

  it("shows the evaluator's words when an attempt has an empty list of checks", () => {
    render(<AttemptRow attempt={attempt([])} />);
    expect(screen.queryByRole("list", { name: "Checks" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Details/ }));
    expect(screen.getByText(/0.50 m from the boundary/)).toBeTruthy();
  });

  it("shows the LiDAR views the model asked for, as thumbnails named by tool", () => {
    const raw = {
      ...JOB,
      attempts: [
        {
          ...JOB.attempts[0],
          observations: ["render_contours", "render_slope"],
          files: {
            "observation-1.png": "/designs/abc123/attempts/1/observation-1.png",
            "observation-2.png": "/designs/abc123/attempts/1/observation-2.png",
          },
        },
      ],
    };
    render(<AttemptRow attempt={parseJob(raw).attempts[0]} />);
    const views = within(screen.getByRole("list", { name: "LiDAR views" }))
      .getAllByRole("img")
      .map((i) => [i.getAttribute("alt"), i.getAttribute("src")]);
    expect(views).toEqual([
      [
        "LiDAR view 1: render contours",
        "/api/designs/abc123/attempts/1/observation-1.png",
      ],
      [
        "LiDAR view 2: render slope",
        "/api/designs/abc123/attempts/1/observation-2.png",
      ],
    ]);
  });

  it("names every check the evaluator makes, in plain words", () => {
    expect(checkLabel("product_footprint")).toBe("The prefab's footprint");
    expect(checkLabel("something_new")).toBe("something new");
  });
});
