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
  /** Rings as one path, e.g. a polygon and its holes (fill-rule evenodd). */
  outline: (rings: Point[][]) => string;
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
  const outline = (parts: Point[][]): string =>
    parts
      .map((ring) => `M${ring.map((p) => point(p).join(",")).join(" L")} Z`)
      .join(" ");
  const fitting = ROUND_LENGTHS_M.filter((m) => m <= width / 3);
  return {
    viewBox: `0 0 ${round(width)} ${round(height)}`,
    paths: rings.map((ring) => outline([ring])),
    scaleBarM: fitting.at(-1) ?? ROUND_LENGTHS_M[0],
    point,
    outline,
  };
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * A point inside `rings` (a polygon and its holes, even-odd) to label it by:
 * the middle of the widest stretch inside along the line half-way up. A
 * bounding box's centre can fall outside a concave outline or in a hole.
 */
export function interiorPoint(rings: Point[][]): Point {
  const ys = rings.flat().map(([, y]) => y);
  const y = (Math.min(...ys) + Math.max(...ys)) / 2;
  const xs: number[] = [];
  for (const ring of rings) {
    for (let i = 0; i + 1 < ring.length; i++) {
      const [[x1, y1], [x2, y2]] = [ring[i], ring[i + 1]];
      if (y1 > y !== y2 > y) xs.push(x1 + ((y - y1) * (x2 - x1)) / (y2 - y1));
    }
  }
  xs.sort((a, b) => a - b);
  let best: Point = rings[0][0];
  let widest = -1;
  for (let i = 0; i + 1 < xs.length; i += 2) {
    if (xs[i + 1] - xs[i] > widest) {
      widest = xs[i + 1] - xs[i];
      best = [(xs[i] + xs[i + 1]) / 2, y];
    }
  }
  return best;
}
