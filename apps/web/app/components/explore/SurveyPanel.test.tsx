import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { parseSurvey } from "@/lib/features";
import { SURVEY } from "@/lib/fixtures";

import type { SurveyControl } from "../useSurvey";
import { SurveyPanel } from "./SurveyPanel";

afterEach(cleanup);

function control(overrides: Partial<SurveyControl> = {}): SurveyControl {
  return {
    survey: parseSurvey(SURVEY),
    missing: null,
    failed: null,
    refused: null,
    saving: false,
    decide: vi.fn(),
    setComplete: vi.fn(),
    ...overrides,
  };
}

describe("SurveyPanel", () => {
  it("lists what was found as chips, each with its decision", () => {
    render(
      <SurveyPanel control={control()} selected={null} onSelect={vi.fn()} />,
    );
    const chips = screen.getAllByRole("button", { name: /^#\d/ });
    expect(chips.map((c) => c.textContent)).toEqual([
      expect.stringMatching(/#1 shed.*Existing building/),
      expect.stringMatching(/#2 tree.*Undecided/),
      expect.stringMatching(/#3 .*Undecided/),
    ]);
  });

  it("marks a decision the survey suggested until the owner makes it", () => {
    const survey = parseSurvey(SURVEY);
    survey.features[0] = { ...survey.features[0], suggested: true };
    render(
      <SurveyPanel
        control={control({ survey })}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    const [first, second] = screen.getAllByRole("button", { name: /^#\d/ });
    expect(first.textContent).toMatch(/Existing building \(suggested\)/);
    expect(second.textContent).not.toMatch(/suggested/);
  });

  it("opens the feature picked on the map, and decides it", () => {
    const decide = vi.fn();
    render(
      <SurveyPanel
        control={control({ decide })}
        selected="2"
        onSelect={vi.fn()}
      />,
    );
    const card = screen.getByRole("group", { name: "What is #2 tree?" });
    fireEvent.click(screen.getByRole("button", { name: "Keep clear" }));
    expect(decide).toHaveBeenCalledWith("2", "keep_clear");
    expect(card).toBeTruthy();
  });

  it("picks a feature from its chip", () => {
    const onSelect = vi.fn();
    render(
      <SurveyPanel control={control()} selected={null} onSelect={onSelect} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /#1 shed/ }));
    expect(onSelect).toHaveBeenCalledWith("1");
  });

  it("says every building is listed", () => {
    const setComplete = vi.fn();
    render(
      <SurveyPanel
        control={control({ setComplete })}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Every building/ }));
    expect(setComplete).toHaveBeenCalledWith(true);
  });

  it("folds to a summary once there is a design, and opens again to edit", () => {
    const onEdit = vi.fn();
    render(
      <SurveyPanel
        control={control()}
        selected={null}
        onSelect={vi.fn()}
        compact
        onEdit={onEdit}
      />,
    );
    expect(
      screen.getByText(/1 building · 0 kept clear · 2 undecided/),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^#\d/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalled();
  });

  it("shows a fixed survey without its controls", () => {
    const survey = { ...parseSurvey(SURVEY), decidedBy: "the owner" };
    render(
      <SurveyPanel
        control={control({ survey })}
        selected="1"
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/as the owner decided it/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Keep clear" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
