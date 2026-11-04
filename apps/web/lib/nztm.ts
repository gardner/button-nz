/**
 * Longitude and latitude (EPSG:4326) to NZTM2000 (EPSG:2193) metres, for
 * drawing the site map's lon/lat layers on an NZTM photo. Transverse
 * Mercator on GRS80 by Krüger's series (Karney 2011, to n⁴): well under a
 * millimetre across New Zealand.
 */

const A_AXIS = 6378137; // GRS80
const F = 1 / 298.257222101;
const LON0 = (173 * Math.PI) / 180; // NZTM's central meridian
const K0 = 0.9996;
const FALSE_EAST = 1600000;
const FALSE_NORTH = 10000000;

const N = F / (2 - F);
const E = Math.sqrt(F * (2 - F));
const RECTIFYING = (A_AXIS / (1 + N)) * (1 + N ** 2 / 4 + N ** 4 / 64);
const ALPHA = [
  N / 2 - (2 * N ** 2) / 3 + (5 * N ** 3) / 16 + (41 * N ** 4) / 180,
  (13 * N ** 2) / 48 - (3 * N ** 3) / 5 + (557 * N ** 4) / 1440,
  (61 * N ** 3) / 240 - (103 * N ** 4) / 140,
  (49561 * N ** 4) / 161280,
];

/** `[lon, lat]` in degrees to NZTM `[east, north]` in metres. */
export function toNztm([lon, lat]: [number, number]): [number, number] {
  const phi = (lat * Math.PI) / 180;
  const dLon = (lon * Math.PI) / 180 - LON0;
  const sinPhi = Math.sin(phi);
  // The tangent of the conformal latitude.
  const t = Math.sinh(Math.atanh(sinPhi) - E * Math.atanh(E * sinPhi));
  const xi0 = Math.atan2(t, Math.cos(dLon));
  const eta0 = Math.atanh(Math.sin(dLon) / Math.sqrt(1 + t * t));
  let xi = xi0;
  let eta = eta0;
  ALPHA.forEach((alpha, i) => {
    const j = 2 * (i + 1);
    xi += alpha * Math.sin(j * xi0) * Math.cosh(j * eta0);
    eta += alpha * Math.cos(j * xi0) * Math.sinh(j * eta0);
  });
  return [
    FALSE_EAST + K0 * RECTIFYING * eta,
    FALSE_NORTH + K0 * RECTIFYING * xi,
  ];
}
