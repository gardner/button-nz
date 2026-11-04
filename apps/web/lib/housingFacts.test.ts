import { describe, expect, it } from "vitest";

import { factsFor, inReefton } from "./housingFacts";

const REEFTON = {
  id: "35-victory-street-reefton",
  address: "35 Victory Street, Reefton",
};
const ELSEWHERE = {
  id: "12-main-road-westport",
  address: "12 Main Road, Westport",
};

describe("inReefton", () => {
  it("knows a site in Reefton by its address or its id", () => {
    expect(inReefton(REEFTON)).toBe(true);
    expect(
      inReefton({ id: "x", address: "2 Caples Street, REEFTON 7830" }),
    ).toBe(true);
    expect(
      inReefton({
        id: "lot-1-beside-12-herald-street-reefton",
        address: "Lot 1",
      }),
    ).toBe(true);
  });

  it("doesn't take a site elsewhere, or a word that merely contains it, for Reefton", () => {
    expect(inReefton(ELSEWHERE)).toBe(false);
    expect(
      inReefton({ id: "reeftonville", address: "1 Reeftonville Road" }),
    ).toBe(false);
  });
});

describe("factsFor", () => {
  it("gives a Reefton site the town's figures, then the national rule, each with its source", () => {
    const facts = factsFor(REEFTON);
    expect(facts.map((f) => f.text)).toEqual([
      "65% of Reefton's residential properties (622 of 959) have room for a real prefab.",
      "439 Reefton backyards have room for a second home.",
      "If 1 in 10 of them added a flat: 43 more homes, +7% on Reefton's 603.",
      "If a quarter did: 109 more homes, housing 109–212 people.",
      "A detached flat of up to 70 m² needs no building consent if it meets Schedule 1A of the Building Act.",
    ]);
    expect(facts.map((f) => f.source)).toEqual([
      "Button NZ town screen, docs/results/town-screen",
      "Button NZ impact report, docs/results/impact",
      "impact report; Stats NZ 2023 Census (CC BY 4.0)",
      "impact report",
      "Building Act 2004, Schedule 1A",
    ]);
  });

  it("gives a site elsewhere only the national rule: no Reefton figure is presented as theirs", () => {
    const facts = factsFor(ELSEWHERE);
    expect(facts).toHaveLength(1);
    expect(facts[0].text).toMatch(/Schedule 1A/);
    expect(facts.some((f) => /Reefton/.test(f.text))).toBe(false);
  });
});
