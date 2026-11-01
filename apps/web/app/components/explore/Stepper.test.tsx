import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { BuildProgress } from "./BuildProgress";
import { Stepper, stepOf } from "./Stepper";

afterEach(cleanup);

describe("stepOf", () => {
  it.each([
    [{}, "find"],
    [{ site: "building" }, "find"],
    [{ site: "ready" }, "survey"],
    [{ site: "ready", design: "running" }, "design"],
    [{ site: "ready", design: "accepted" }, "check"],
    [{ site: "ready", design: "accepted", prefabs: true }, "prefab"],
    [{ site: "ready", design: "failed" }, "check"],
  ] as const)("is where the journey has got to: %o", (state, step) => {
    expect(stepOf(state)).toBe(step);
  });
});

describe("Stepper", () => {
  it("marks the steps done, the one on now, and those to come", () => {
    render(<Stepper current="design" />);
    const steps = screen.getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual([
      expect.stringContaining("Find"),
      expect.stringContaining("Survey"),
      expect.stringContaining("Design"),
      expect.stringContaining("Check"),
      expect.stringContaining("Prefab"),
    ]);
    expect(steps[2].getAttribute("aria-current")).toBe("step");
    expect(steps[0].dataset.state).toBe("done");
    expect(steps[4].dataset.state).toBe("todo");
  });
});

describe("BuildProgress", () => {
  it("says what the server is doing now", () => {
    render(
      <BuildProgress
        address="35 Victory Street, Reefton"
        status="building"
        step="terrain"
        error={null}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain(
      "Reading the LiDAR",
    );
    expect(screen.getByText("35 Victory Street, Reefton")).toBeTruthy();
  });

  it("says plainly when there is no LiDAR there", () => {
    render(
      <BuildProgress
        address="1 Far Road"
        status="no_lidar"
        step={null}
        error="LINZ has no 1 m LiDAR here"
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "No LiDAR here yet",
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "LINZ has no 1 m LiDAR here",
    );
  });

  it("says why a build failed", () => {
    render(
      <BuildProgress
        address="1 Far Road"
        status="failed"
        step={null}
        error="the survey failed"
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "the survey failed",
    );
  });
});
