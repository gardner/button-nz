/**
 * What a site's build has found so far (#152), as GET /sites/{id}/progress
 * serves it: the frame every step is drawn in, the title's parcels and the
 * buildings around them, the LiDAR's preview, the aerial, and SAM 3.1's
 * survey concept by concept. Coordinates are NZTM metres, drawn in a square
 * frame with north at the top.
 */

import {
  type Fields,
  asList,
  list,
  number,
  numbers,
  optional,
  record,
  text,
} from "./fields";
import { API, request } from "./http";

export type BBox = [number, number, number, number]; // west, south, east, north
export type Ring = [number, number][];

export interface Picture {
  bbox: BBox;
  url: string; // through the same-origin proxy
}

export interface Found {
  concept: string;
  rings: Ring[];
}

export interface SurveyProgress {
  concepts: string[];
  asking: string | null; // the concept SAM 3.1 is being asked about now
  found: Found[]; // each concept SAM has answered, in the order asked
}

export interface BuildProgress {
  frame: BBox | null; // none until the parcels are found
  parcels: Ring[];
  buildings: Ring[];
  terrain: (Picture & { lowM: number; highM: number }) | null;
  aerial: Picture | null;
  survey: SurveyProgress | null;
}

export async function getProgress(siteId: string): Promise<BuildProgress> {
  return parseProgress(
    await request(`/sites/${encodeURIComponent(siteId)}/progress`),
  );
}

export function parseProgress(raw: unknown): BuildProgress {
  const shown = record(raw, "build progress");
  return {
    frame: shown.frame === null ? null : bbox(shown.frame),
    parcels: rings(list(shown, "parcels")),
    buildings: rings(list(shown, "buildings")),
    terrain: optional(shown, "terrain", (f, k) => {
      const terrain = record(f[k], k);
      return {
        ...picture(terrain),
        lowM: number(terrain, "low_m"),
        highM: number(terrain, "high_m"),
      };
    }),
    aerial: optional(shown, "aerial", (f, k) => picture(record(f[k], k))),
    survey: optional(shown, "survey", (f, k) => survey(record(f[k], k))),
  };
}

/** A square around `frame`: its longer side, centred on it. */
export interface Square {
  west: number;
  north: number;
  side: number;
}

export function squareFrame([west, south, east, north]: BBox): Square {
  const side = Math.max(east - west, north - south);
  return {
    west: (west + east - side) / 2,
    north: (south + north + side) / 2,
    side,
  };
}

/** Where `bbox` sits in `square`, in metres from its top-left corner. */
export function placed([west, south, east, north]: BBox, square: Square) {
  return {
    x: west - square.west,
    y: square.north - north,
    width: east - west,
    height: north - south,
  };
}

/** `ring` as an SVG path in `square`'s metres. */
export function ringPath(ring: Ring, square: Square): string {
  const points = ring.map(
    ([x, y]) => `${round(x - square.west)} ${round(square.north - y)}`,
  );
  return `M${points.join("L")}Z`;
}

function round(metres: number): number {
  return Math.round(metres * 100) / 100;
}

function bbox(value: unknown): BBox {
  return numbers(value, 4) as BBox;
}

function rings(values: unknown[]): Ring[] {
  return values.map((ring) =>
    asList(ring, "ring").map((point) => numbers(point, 2) as [number, number]),
  );
}

function picture(fields: Fields): Picture {
  return { bbox: bbox(fields.bbox), url: `${API}${text(fields, "url")}` };
}

function survey(fields: Fields): SurveyProgress {
  return {
    concepts: list(fields, "concepts").map((c) =>
      text({ concept: c }, "concept"),
    ),
    asking: optional(fields, "asking", text),
    found: list(fields, "found").map((raw) => {
      const found = record(raw, "found");
      return {
        concept: text(found, "concept"),
        rings: rings(list(found, "rings")),
      };
    }),
  };
}
