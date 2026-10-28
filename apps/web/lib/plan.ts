/**
 * A true-scale site plan in SVG user units of one metre, north up. NZTM
 * (EPSG:2193) is a projected metre grid, so a plan needs only a shift and a
 * flip of the northing: no reprojection, no basemap.
 */

import type { Point } from "./api";

export interface PlanView {
  viewBox: string;
  paths: string[]; // one closed path per ring
  scaleBarM: number;
  point: (p: Point) => Point;
}

const ROUND_LENGTHS_M = [1, 2, 5, 10, 20, 50, 100, 200, 500];

export function planView(
  rings: Point[][],
  extent: [number, number, number, number],
  marginM: number,
): PlanView {
  const [west, south, east, north] = extent;
  const width = east - west + 2 * marginM;
  const height = north - south + 2 * marginM;
  const point = ([x, y]: Point): Point => [
    round(x - west + marginM),
    round(north - y + marginM),
  ];
  const paths = rings.map(
    (ring) => `M${ring.map((p) => point(p).join(",")).join(" L")} Z`,
  );
  const fitting = ROUND_LENGTHS_M.filter((m) => m <= width / 3);
  return {
    viewBox: `0 0 ${round(width)} ${round(height)}`,
    paths,
    scaleBarM: fitting.at(-1) ?? ROUND_LENGTHS_M[0],
    point,
  };
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
