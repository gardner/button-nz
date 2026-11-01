import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SURVEY } from "@/lib/fixtures";

import { useSurvey } from "./useSurvey";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useSurvey", () => {
  it("drops the '(suggested)' mark once the owner confirms the list", async () => {
    const suggested = {
      ...SURVEY,
      features: SURVEY.features.map((f, i) =>
        i === 0
          ? { ...f, properties: { ...f.properties, suggested: true } }
          : f,
      ),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const body =
          init?.method === "PUT"
            ? { survey_id: SURVEY.survey_id, buildings_complete: true }
            : suggested;
        return Promise.resolve(new Response(JSON.stringify(body)));
      }),
    );
    const { result } = renderHook(() => useSurvey());
    await waitFor(() => expect(result.current.survey).not.toBeNull());
    expect(result.current.survey?.features[0].suggested).toBe(true);
    act(() => result.current.setComplete(true));
    await waitFor(() =>
      expect(result.current.survey?.buildingsComplete).toBe(true),
    );
    // The server stores every suggestion as the owner's own when they confirm.
    expect(result.current.survey?.features.map((f) => f.suggested)).toEqual(
      result.current.survey?.features.map(() => false),
    );
  });
});
