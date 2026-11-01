/**
 * GeoJSON layers for the map, in EPSG:4326 (RFC 7946), as the API sends
 * them. Each feature's geometry is checked to be one the map can draw, with
 * every position a pair of numbers; its properties are read by the caller.
 */

import {
  ApiError,
  type Fields,
  asList,
  isRecord,
  list,
  record,
  text,
} from "./fields";

export type LonLat = [number, number];
export type Bounds = [number, number, number, number]; // west, south, east, north

const DEPTHS = {
  Point: 0,
  LineString: 1,
  MultiLineString: 2,
  Polygon: 2,
  MultiPolygon: 3,
} as const;

export type GeometryType = keyof typeof DEPTHS;

export interface Geometry {
  type: GeometryType;
  coordinates: unknown; // nested positions, checked to the type's depth
}

export interface Feature<P> {
  id: string | number | undefined;
  properties: P;
  geometry: Geometry;
}

export interface FeatureCollection<P> {
  type: "FeatureCollection";
  features: Feature<P>[];
}

/** A FeatureCollection whose properties `read` turns into a `P`. */
export function parseCollection<P>(
  raw: unknown,
  what: string,
  read: (properties: Fields) => P,
): FeatureCollection<P> {
  const collection = record(raw, what);
  if (collection.type !== "FeatureCollection")
    throw new ApiError(`expected ${what} to be a FeatureCollection`);
  return {
    type: "FeatureCollection",
    features: list(collection, "features").map((f) => parseFeature(f, read)),
  };
}

function parseFeature<P>(raw: unknown, read: (p: Fields) => P): Feature<P> {
  const feature = record(raw, "feature");
  const geometry = record(feature.geometry, "geometry");
  const type = text(geometry, "type");
  if (!(type in DEPTHS)) throw new ApiError(`can't draw a ${type}`);
  const depth = DEPTHS[type as GeometryType];
  checkPositions(geometry.coordinates, depth);
  const id = feature.id;
  return {
    id: typeof id === "string" || typeof id === "number" ? id : undefined,
    properties: read(isRecord(feature.properties) ? feature.properties : {}),
    geometry: { type: type as GeometryType, coordinates: geometry.coordinates },
  };
}

function checkPositions(value: unknown, depth: number): void {
  if (depth === 0) {
    const position = asList(value, "position");
    if (
      position.length < 2 ||
      !position.every((n) => typeof n === "number" && Number.isFinite(n))
    )
      throw new ApiError("expected a position to be numbers");
    return;
  }
  for (const part of asList(value, "coordinates"))
    checkPositions(part, depth - 1);
}

/** The west, south, east and north of every position in `layers`, or null. */
export function boundsOf(
  ...layers: FeatureCollection<unknown>[]
): Bounds | null {
  let bounds: Bounds | null = null;
  const visit = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number") {
      const [lon, lat] = value as number[];
      bounds = bounds
        ? [
            Math.min(bounds[0], lon),
            Math.min(bounds[1], lat),
            Math.max(bounds[2], lon),
            Math.max(bounds[3], lat),
          ]
        : [lon, lat, lon, lat];
      return;
    }
    value.forEach(visit);
  };
  for (const layer of layers)
    for (const f of layer.features) visit(f.geometry.coordinates);
  return bounds;
}
