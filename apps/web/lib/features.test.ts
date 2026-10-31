import { describe, expect, it } from "vitest";

import { ApiError } from "./fields";
import { parseFeature, parseSurvey } from "./features";
import { SURVEY } from "./fixtures";

const [SHED, TREE, RAISED] = SURVEY.features;

describe("parseSurvey", () => {
  it("reads the survey and each feature's decision", () => {
    const survey = parseSurvey(SURVEY);
    expect(survey.id).toBe("s1");
    expect(survey.buildingsComplete).toBe(false);
    expect(survey.decidedBy).toBeNull();
    expect(survey.features.map((f) => f.decision)).toEqual([
      "building",
      null,
      null,
    ]);
    expect(survey.features[0]).toMatchObject({
      id: "1",
      concept: "shed",
      score: 0.91,
      areaM2: 12.25,
      maxHeightM: 2.6,
      status: "agrees",
      note: "The LiDAR shows 4% of it under 0.5 m.",
    });
    expect(survey.features[2]).toMatchObject({ score: null, maxHeightM: null });
  });

  it("reads who decided a survey this server has fixed", () => {
    const fixed = { ...SURVEY, fixed: true, decided_by: "the owner" };
    expect(parseSurvey(fixed).decidedBy).toBe("the owner");
  });

  it("refuses a fixed survey that doesn't say who decided it", () => {
    expect(() => parseSurvey({ ...SURVEY, fixed: true })).toThrow(ApiError);
  });

  it("reads a polygon and a multipolygon as lists of polygons", () => {
    const [shed, tree] = parseSurvey(SURVEY).features;
    expect(shed.polygons).toHaveLength(1);
    expect(shed.polygons[0][0][1]).toEqual([1005.5, 2002]);
    expect(tree.polygons).toHaveLength(2);
    expect(tree.polygons[1][0][0]).toEqual([1014, 2010]);
  });

  it("refuses a survey that isn't in NZTM", () => {
    expect(() => parseSurvey({ ...SURVEY, crs: "EPSG:4326" })).toThrow(
      "EPSG:2193",
    );
  });

  const withProperties = (properties: object) => ({
    ...SHED,
    properties: { ...SHED.properties, ...properties },
  });

  it.each([
    [withProperties({ status: "maybe" })],
    [withProperties({ decision: "demolish" })],
    [withProperties({ area_m2: null })],
    [withProperties({ note: null })],
    [{ ...SHED, id: 1 }],
    [{ ...SHED, geometry: { type: "Point", coordinates: [1, 2] } }],
    [{ ...TREE, geometry: { ...TREE.geometry, type: "Polygon" } }],
    [{ ...RAISED, geometry: { type: "Polygon", coordinates: [[[1, 2, 3]]] } }],
  ])("rejects a malformed feature", (raw) => {
    expect(() => parseFeature(raw)).toThrow(ApiError);
  });

  it("rejects a survey without its id or completeness", () => {
    expect(() => parseSurvey({ ...SURVEY, survey_id: undefined })).toThrow(
      ApiError,
    );
    expect(() => parseSurvey({ ...SURVEY, buildings_complete: "no" })).toThrow(
      ApiError,
    );
  });
});
