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
  labelAt: LonLat; // where its label hangs from: just below it
}

/** The placement as the map draws it. */
export function massingLayers(placement: Placement): MassingLayers {
  return {
    walls: polygon("walls", placement.walls),
    outline: polygon("outline", placement.outline),
    labelAt: [middle(placement.walls), south(placement.outline)],
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

/** The mean longitude of a closed ring's corners (its first is its last). */
function middle(ring: LonLat[]): number {
  const corners = ring.slice(0, -1);
  return corners.reduce((sum, [lon]) => sum + lon, 0) / corners.length;
}

/** A ring's southernmost latitude. */
function south(ring: LonLat[]): number {
  return Math.min(...ring.map(([, lat]) => lat));
}
