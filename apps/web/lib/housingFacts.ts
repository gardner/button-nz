/** Facts about housing to read while Muse writes its script: each one from a
 * report, with its source shown under it. Nothing here is invented. */

export interface HousingFact {
  text: string;
  source: string;
}

/** Reefton's own figures: shown only on a site in Reefton. */
const REEFTON: readonly HousingFact[] = [
  {
    text: "65% of Reefton's residential properties (622 of 959) have room for a real prefab.",
    source: "Button NZ town screen, docs/results/town-screen",
  },
  {
    text: "439 Reefton backyards have room for a second home.",
    source: "Button NZ impact report, docs/results/impact",
  },
  {
    text: "If 1 in 10 of them added a flat: 43 more homes, +7% on Reefton's 603.",
    source: "impact report; Stats NZ 2023 Census (CC BY 4.0)",
  },
  {
    text: "If a quarter did: 109 more homes, housing 109–212 people.",
    source: "impact report",
  },
];

/** True wherever the site is in New Zealand. */
const EVERYWHERE: readonly HousingFact[] = [
  {
    text: "A detached flat of up to 70 m² needs no building consent if it meets Schedule 1A of the Building Act.",
    source: "Building Act 2004, Schedule 1A",
  },
];

/** Whether the site is in Reefton, as its address or id says. */
export function inReefton(site: { id: string; address: string }): boolean {
  return /\breefton\b/i.test(`${site.address} ${site.id}`);
}

/** The facts that are true of `site`: no Reefton figure on a site elsewhere. */
export function factsFor(site: { id: string; address: string }): HousingFact[] {
  return inReefton(site) ? [...REEFTON, ...EVERYWHERE] : [...EVERYWHERE];
}
