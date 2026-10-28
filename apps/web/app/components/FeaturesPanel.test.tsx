import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SURVEY } from "@/lib/fixtures";

import { FeaturesPanel } from "./FeaturesPanel";
import { useSurvey } from "./useSurvey";

const TREE = SURVEY.features[1];

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function serve(...responses: Response[]): ReturnType<typeof vi.fn> {
  const fetch = vi.fn();
  for (const response of responses) fetch.mockResolvedValueOnce(response);
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function Confirming() {
  return <FeaturesPanel {...useSurvey()} />;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function feature(name: string): Promise<HTMLElement> {
  return screen.findByRole("article", { name });
}

function pressed(card: HTMLElement): string[] {
  return within(card)
    .getAllByRole("button", { pressed: true })
    .map((b) => b.textContent ?? "");
}

describe("FeaturesPanel", () => {
  it("shows what was found and measured, flagging what needs a person", async () => {
    serve(respond(SURVEY));
    render(<Confirming />);
    const shed = await feature("#1 shed");
    expect(within(shed).getByText(/12\.3 m² · up to 2\.6 m tall/)).toBeTruthy();
    expect(within(shed).getByText("LiDAR agrees")).toBeTruthy();
    expect(within(shed).getByText(/4% of it under 0\.5 m/)).toBeTruthy();
    expect(within(shed).queryByText("Needs your judgement")).toBeNull();
    const tree = await feature("#2 tree");
    expect(within(tree).getByText("LiDAR disagrees")).toBeTruthy();
    expect(within(tree).getByText("Needs your judgement")).toBeTruthy();
    const raised = await feature("#3 unlabelled");
    expect(within(raised).getByText(/no height from the LiDAR/)).toBeTruthy();
    expect(within(raised).getByText("Needs your judgement")).toBeTruthy();
  });

  it("shows each feature's current decision as pressed", async () => {
    serve(respond(SURVEY));
    render(<Confirming />);
    expect(pressed(await feature("#1 shed"))).toEqual(["Existing building"]);
    const tree = await feature("#2 tree");
    expect(within(tree).queryAllByRole("button", { pressed: true })).toEqual(
      [],
    );
    expect(within(tree).getAllByRole("button")).toHaveLength(3);
  });

  it("records a decision", async () => {
    const decided = {
      ...TREE,
      properties: { ...TREE.properties, decision: "keep_clear" },
    };
    const fetch = serve(respond(SURVEY), respond(decided));
    render(<Confirming />);
    const tree = await feature("#2 tree");
    await userEvent.click(
      within(tree).getByRole("button", { name: "Keep clear" }),
    );
    expect(
      await within(tree).findByRole("button", { pressed: true }),
    ).toHaveProperty("textContent", "Keep clear");
    const [url, init] = fetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/site/features/2");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({
      decision: "keep_clear",
      survey_id: "s1",
    });
  });

  it("says why a decision wasn't saved, and keeps the one that was", async () => {
    serve(respond(SURVEY), respond({ detail: "Bad Gateway" }, 502));
    render(<Confirming />);
    const shed = await feature("#1 shed");
    await userEvent.click(within(shed).getByRole("button", { name: "Ignore" }));
    expect(await screen.findByText(/Not saved: Bad Gateway/)).toBeTruthy();
    expect(pressed(shed)).toEqual(["Existing building"]);
  });

  it("shows why every building can't be listed yet", async () => {
    const detail = "decide what these are first: 2, 3";
    serve(respond(SURVEY), respond({ detail }, 409));
    render(<Confirming />);
    const complete = await screen.findByRole("checkbox", {
      name: "Every building on the site is listed",
    });
    await userEvent.click(complete);
    expect(await screen.findByText(new RegExp(detail))).toBeTruthy();
    expect((complete as HTMLInputElement).checked).toBe(false);
  });

  it("says every building is listed", async () => {
    const fetch = serve(
      respond(SURVEY),
      respond({ survey_id: "s1", buildings_complete: true }),
    );
    render(<Confirming />);
    const complete = await screen.findByRole("checkbox", {
      name: "Every building on the site is listed",
    });
    await userEvent.click(complete);
    await vi.waitFor(() =>
      expect((complete as HTMLInputElement).checked).toBe(true),
    );
    const init = fetch.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      buildings_complete: true,
      survey_id: "s1",
    });
  });

  it("explains, in the API's words, that there is no survey yet", async () => {
    const detail = "no survey yet: run python -m button_nz.perception.survey";
    serve(respond({ detail }, 404));
    render(<Confirming />);
    expect(await screen.findByText(detail)).toBeTruthy();
    expect(screen.queryByText(/Could not/)).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("says why the survey couldn't be read", async () => {
    serve(respond({ ...SURVEY, crs: "EPSG:4326" }));
    render(<Confirming />);
    expect(
      await screen.findByText(/Could not load the survey: .*EPSG:2193/),
    ).toBeTruthy();
  });
});
