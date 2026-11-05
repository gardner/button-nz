/**
 * The instant massing (#188): where a home of the run's plan fits, which the
 * API knows in well under a second as a design starts. Shown in words in the
 * "Muse at work" overlay, and on the map as a plain, provisional block until
 * the accepted design replaces it.
 */

import type { Placement } from "./api";
import type { FeatureCollection, LonLat } from "./geo";

/** The first thing the run has to say: how soon, what fits, how far in. */
export function fitsWords(placement: Placement): string {
  const { plan, foundInS, clearances } = placement;
  const soon =
    foundInS < 1 ? "In under a second" : `In ${Math.round(foundInS)} s`;
  return (
    `${soon}: a ${metres(plan.lengthM)} × ${metres(plan.widthM)} m home fits here, ` +
    `${clearances.titleBoundaryM.toFixed(1)} m from the boundary; Muse is now designing it.`
  );
}

/** A plan's side in metres, as short as it is exact: 10, 4.8. */
function metres(value: number): string {
  return String(Number(value.toFixed(2)));
}

const CLEARANCES: [keyof Placement["clearances"], string][] = [
  ["titleBoundaryM", "the boundary"],
  ["sectionLineM", "the section line"],
  ["buildingM", "the nearest building"],
  ["streetEdgeM", "the street"],
];

/** Each clearance the evaluator measured, in words. */
export function clearanceWords(placement: Placement): string[] {
  return CLEARANCES.flatMap(([key, what]) => {
    const value = placement.clearances[key];
    return value === null ? [] : [`${value.toFixed(1)} m from ${what}`];
  });
}

export interface MassingLayers {
  walls: FeatureCollection<null>;
  outline: FeatureCollection<null>;
  centre: LonLat; // where its label goes
}

/** The placement as the map draws it. */
export function massingLayers(placement: Placement): MassingLayers {
  return {
    walls: polygon("walls", placement.walls),
    outline: polygon("outline", placement.outline),
    centre: centre(placement.walls),
  };
}

function polygon(id: string, ring: LonLat[]): FeatureCollection<null> {
  return {
    type: "FeatureCollection",
    features: [
      {
        id,
        properties: null,
        geometry: { type: "Polygon", coordinates: [ring] },
      },
    ],
  };
}

/** The mean of a closed ring's corners (its first is its last). */
function centre(ring: LonLat[]): LonLat {
  const corners = ring.slice(0, -1);
  const mean = (i: 0 | 1) =>
    corners.reduce((sum, p) => sum + p[i], 0) / corners.length;
  return [mean(0), mean(1)];
}
