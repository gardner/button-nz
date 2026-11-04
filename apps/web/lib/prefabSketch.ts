/**
 * A small isometric sketch of a prefab (#154), drawn from what its supplier
 * publishes: its outside footprint, the roof form its material shows first,
 * its pitch where stated, and its colours. Ours to show, unlike the
 * suppliers' photos. Every sketch in a list shares one scale, so a longer
 * home is drawn longer. The stud height, and the pitch where it isn't
 * published, are illustrative.
 */

import type { Product, RoofForm } from "./products";

export type Point = [number, number];

export interface Face {
  part: "walls" | "roof";
  points: Point[]; // in the tile's pixels, y down
  fill: string;
}

export interface Sketched {
  faces: Face[]; // only those turned to the viewer: none covers another
  roof: RoofForm;
  description: string;
}

export type Sketch = Sketched | { missing: string };

/** The tile every sketch is drawn in, and the pixels a metre takes in it. */
export interface SketchScale {
  pxPerM: number;
  width: number;
  height: number;
}

const TILE = { width: 80, height: 44 };
const PAD_PX = 2;
const STUD_M = 2.7; // floor to eaves: illustrative
const PITCH_DEG: Record<RoofForm, number> = {
  mono: 10, // where the supplier doesn't publish one: illustrative
  gable: 25,
  hip: 25,
  flat: 0,
};
// The camera: turned 20° from square to the long side, and raised 30°, so
// a long, narrow home reads long and its walls show under its roof.
const TURN = (20 * Math.PI) / 180;
const RAISE = (30 * Math.PI) / 180;
/** Where the camera looks from: the direction the drawing flattens. */
const VIEWER: Corner = [
  Math.sin(TURN) * Math.cos(RAISE),
  Math.cos(TURN) * Math.cos(RAISE),
  Math.sin(RAISE),
];

/** How each side catches the light, from the upper front: the long side
 * the viewer faces is the colour as published. */
const LIGHT = { side: 1, end: 0.8, away: 0.72, toward: 1.12, hip: 0.92 };
type Facing = keyof typeof LIGHT;

type Corner = [number, number, number]; // along the length, across, up: metres
interface Plane {
  part: Face["part"];
  facing: Facing;
  corners: Corner[];
}

/** One scale for every product in `products` that can be drawn: the
 * largest fills the tile. */
export function sketchScale(products: Product[]): SketchScale {
  const sizes = products.flatMap((p) => {
    const planes = p.placeable ? planesOf(p) : null;
    return planes ? [extent(planes.flatMap((pl) => pl.corners.map(seen)))] : [];
  });
  const across = Math.max(1, ...sizes.map((s) => s.across));
  const tall = Math.max(1, ...sizes.map((s) => s.tall));
  const pxPerM = Math.min(
    (TILE.width - 2 * PAD_PX) / across,
    (TILE.height - 2 * PAD_PX) / tall,
  );
  return { pxPerM, ...TILE };
}

export function sketch(product: Product, scale: SketchScale): Sketch {
  if (!product.placeable)
    return { missing: "its figures aren't a published footprint" };
  const planes = planesOf(product)?.filter(facesTheViewer);
  if (!planes) return { missing: "its roof isn't published" };
  const [roof, ...others] = product.appearance.roofForms;
  const projected = planes.map((pl) => pl.corners.map(seen));
  const { left, bottom, across } = extent(projected.flat());
  const dx = (scale.width - across * scale.pxPerM) / 2 - left * scale.pxPerM;
  const dy = scale.height - PAD_PX - bottom * scale.pxPerM;
  const colours = product.appearance;
  return {
    faces: planes.map((pl, i) => ({
      part: pl.part,
      points: projected[i].map(([x, y]) => [
        round(x * scale.pxPerM + dx),
        round(y * scale.pxPerM + dy),
      ]),
      fill: shade(
        pl.part === "walls" ? colours.walls : colours.roof,
        pl.facing,
      ),
    })),
    roof,
    description:
      `Sketch of the ${product.model}: ${product.lengthM} × ${product.widthM} m, ` +
      `${roof} roof${others.length ? ` (or ${others.join(" or ")})` : ""}`,
  };
}

/** Its walls and roof in metres, the length along x, seen from the front
 * right; none if its roof isn't published. */
function planesOf(product: Product): Plane[] | null {
  const roof = product.appearance.roofForms[0];
  if (!roof) return null;
  const length = Math.max(product.lengthM, product.widthM);
  const width = Math.min(product.lengthM, product.widthM);
  const pitch = product.appearance.roofPitchDeg ?? PITCH_DEG[roof];
  const tan = Math.tan((pitch * Math.PI) / 180);
  const run = roof === "mono" ? width : width / 2;
  return ROOFS[roof](length, width, STUD_M, run * tan);
}

type Build = (l: number, w: number, h: number, rise: number) => Plane[];

const side = (l: number, w: number, h: number): Plane => ({
  part: "walls",
  facing: "side",
  corners: [
    [0, w, 0],
    [l, w, 0],
    [l, w, h],
    [0, w, h],
  ],
});

const end = (l: number, tops: Corner[]): Plane => ({
  part: "walls",
  facing: "end",
  corners: [[l, tops.at(-1)![1], 0], [l, tops[0][1], 0], ...tops],
});

const roofPlane = (facing: Facing, corners: Corner[]): Plane => ({
  part: "roof",
  facing,
  corners,
});

const ROOFS: Record<RoofForm, Build> = {
  gable: (l, w, h, r) => [
    side(l, w, h),
    end(l, [
      [l, w, h],
      [l, w / 2, h + r],
      [l, 0, h],
    ]),
    roofPlane("away", [
      [0, 0, h],
      [l, 0, h],
      [l, w / 2, h + r],
      [0, w / 2, h + r],
    ]),
    roofPlane("toward", [
      [0, w / 2, h + r],
      [l, w / 2, h + r],
      [l, w, h],
      [0, w, h],
    ]),
  ],
  mono: (l, w, h, r) => [
    side(l, w, h), // the low side faces the viewer
    end(l, [
      [l, w, h],
      [l, 0, h + r],
    ]),
    roofPlane("toward", [
      [0, 0, h + r],
      [l, 0, h + r],
      [l, w, h],
      [0, w, h],
    ]),
  ],
  hip: (l, w, h, r) => {
    const ridge: [Corner, Corner] = [
      [w / 2, w / 2, h + r],
      [l - w / 2, w / 2, h + r],
    ];
    return [
      side(l, w, h),
      end(l, [
        [l, w, h],
        [l, 0, h],
      ]),
      roofPlane("away", [[0, 0, h], [l, 0, h], ridge[1], ridge[0]]),
      roofPlane("hip", [[0, w, h], [0, 0, h], ridge[0]]),
      roofPlane("hip", [[l, 0, h], [l, w, h], ridge[1]]),
      // Starts at the eaves: on a square plan the ridge is a point, and its
      // first three corners must still span the plane.
      roofPlane("toward", [[l, w, h], [0, w, h], ridge[0], ridge[1]]),
    ];
  },
  flat: (l, w, h) => [
    side(l, w, h),
    end(l, [
      [l, w, h],
      [l, 0, h],
    ]),
    roofPlane("toward", [
      [0, 0, h],
      [l, 0, h],
      [l, w, h],
      [0, w, h],
    ]),
  ],
};

/** Whether `plane` is turned to the `VIEWER`, up and to the front right.
 * Every roof form here is convex, so the planes that are never overlap. */
function facesTheViewer(plane: Plane, _: number, body: Plane[]): boolean {
  const [a, b, c] = plane.corners;
  const u = minus(b, a);
  const v = minus(c, a);
  const normal: Corner = [
    u[1] * v[2] - u[2] * v[1],
    u[2] * v[0] - u[0] * v[2],
    u[0] * v[1] - u[1] * v[0],
  ];
  const out = minus(
    centre(plane.corners),
    centre(body.flatMap((p) => p.corners)),
  );
  const outward = dot(normal, out) < 0 ? -1 : 1;
  return outward * dot(normal, VIEWER) > 1e-9;
}

function minus(p: Corner, q: Corner): Corner {
  return [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
}

function dot(p: Corner, q: Corner): number {
  return p[0] * q[0] + p[1] * q[1] + p[2] * q[2];
}

function centre(corners: Corner[]): Corner {
  const sum = corners.reduce((s, c) => [s[0] + c[0], s[1] + c[1], s[2] + c[2]]);
  return [
    sum[0] / corners.length,
    sum[1] / corners.length,
    sum[2] / corners.length,
  ];
}

/** Seen from the `VIEWER`, a metre to a unit: the length to the right,
 * across into the picture, up up. */
function seen([x, y, z]: Corner): Point {
  return [
    x * Math.cos(TURN) - y * Math.sin(TURN),
    (x * Math.sin(TURN) + y * Math.cos(TURN)) * Math.sin(RAISE) -
      z * Math.cos(RAISE),
  ];
}

function extent(points: Point[]) {
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  return { left, bottom, across: Math.max(...xs) - left, tall: bottom - top };
}

/** `hex` in `facing`'s light: darker, or towards white past 1. */
function shade(hex: string, facing: Facing): string {
  const k = LIGHT[facing];
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const lit = channels.map((c) =>
    Math.round(k <= 1 ? c * k : c + (255 - c) * (k - 1)),
  );
  return `#${lit.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

function round(px: number): number {
  return Math.round(px * 100) / 100;
}
