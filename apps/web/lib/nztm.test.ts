import { describe, expect, it } from "vitest";

import { toNztm } from "./nztm";

/** Points projected with pyproj (EPSG:4326 to EPSG:2193), as the server does. */
const KNOWN: [[number, number], [number, number]][] = [
  [
    [173, -41],
    [1600000.0, 5461242.938201998],
  ], // on the central meridian
  // A building corner at 42 Church Street, Reefton, and the site's corner.
  [
    [171.8628767, -42.1174514],
    [1505998.8967269587, 5336557.519809503],
  ],
  [
    [171.8629584, -42.1178751],
    [1506006.276819701, 5336510.5648712255],
  ],
  [
    [174.7762, -41.2865],
    [1748735.5530602792, 5427916.478887198],
  ], // Wellington
  // The far ends of the country: Fiordland and East Cape.
  [
    [166.5, -46.5],
    [1101299.2562429812, 4829834.135055269],
  ],
  [
    [178.5, -37.6],
    [2085688.0588215177, 5824316.10537957],
  ],
];

describe("toNztm", () => {
  it("projects longitude and latitude to NZTM as pyproj does, to the millimetre", () => {
    for (const [lonLat, [east, north]] of KNOWN) {
      const [x, y] = toNztm(lonLat);
      expect(Math.abs(x - east)).toBeLessThan(0.001);
      expect(Math.abs(y - north)).toBeLessThan(0.001);
    }
  });
});
