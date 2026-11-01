/** API responses for sites, addresses and the town map (issue #86's
 * contract), shared by the tests and, until the API serves them, the dev mock. */

function square(lon: number, lat: number, d: number) {
  return [
    [
      [lon, lat],
      [lon + d, lat],
      [lon + d, lat + d],
      [lon, lat + d],
      [lon, lat],
    ],
  ];
}

/** GET /addresses?q=35 Victory */
export const ADDRESSES = {
  addresses: [
    {
      id: 1907458,
      address: "35 Victory Street, Reefton",
      town: "Reefton",
      lonlat: [171.8622, -42.1158],
    },
    {
      id: 1907459,
      address: "35 Victory Road, Laingholm, Auckland",
      town: "Auckland",
      lonlat: [174.6211, -36.9667],
    },
  ],
};

/** GET /sites/{id} while it is being built. */
export const SITE_BUILDING = {
  id: "addr-1907458",
  address: "35 Victory Street, Reefton",
  status: "building",
  step: "terrain",
  error: null,
  bounds: null,
  site: null,
};

/** GET /sites/{id} once it is ready: bounds in lon/lat, and under "site"
 * everything GET /site returns (whose own "address" is an NZTM point). */
export const SITE_READY = {
  id: "35-victory-street-reefton",
  address: "35 Victory Street, Reefton",
  status: "ready",
  step: null,
  error: null,
  bounds: [171.8619, -42.1161, 171.8625, -42.1155],
  site: {
    name: "35 Victory Street, Reefton",
    title: "354613",
    valuation_number: "1905027200",
    crs: "EPSG:2193",
    address: [1505941.6, 5336793.7],
    extent: [1505926.13, 5336777.48, 1505969.74, 5336822.22],
    parcels: { type: "FeatureCollection", features: [] },
    sources: {},
    open_items: [],
    aerial: null,
  },
};

/** GET /town/reefton: three sections, one of each category. */
export const TOWN = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: 1,
      properties: { id: 1, category: "clear" },
      geometry: {
        type: "Polygon",
        coordinates: square(171.86, -42.116, 0.0002),
      },
    },
    {
      type: "Feature",
      id: 2,
      properties: { id: 2, category: "outlines" },
      geometry: {
        type: "Polygon",
        coordinates: square(171.861, -42.116, 0.0002),
      },
    },
    {
      type: "Feature",
      id: 3,
      properties: { id: 3, category: "none" },
      geometry: {
        type: "Polygon",
        coordinates: square(171.862, -42.116, 0.0002),
      },
    },
  ],
};

function collection(...features: object[]) {
  return { type: "FeatureCollection", features };
}

function polygon(
  id: number | string,
  properties: object,
  coordinates: unknown,
) {
  return {
    type: "Feature",
    id,
    properties,
    geometry: { type: "Polygon", coordinates },
  };
}

/** GET /sites/{id}/map */
export const SITE_MAP = {
  parcels: collection(
    polygon(
      3652040,
      { appellation: "Section 700 Town of Reefton" },
      square(171.8619, -42.1161, 0.0003),
    ),
  ),
  buildings: collection(),
  features: collection(
    polygon(
      "1",
      { concept: "shed", status: "agrees", decision: "ignore" },
      square(171.862, -42.116, 0.00004),
    ),
    polygon(
      "3",
      { concept: "tree", status: "agrees", decision: "keep_clear" },
      square(171.8621, -42.1159, 0.00005),
    ),
  ),
  setback: collection(
    polygon("setback", {}, square(171.8619, -42.1161, 0.0003)),
  ),
  halos: collection(),
  keep_clear: collection(polygon("3", {}, square(171.8621, -42.1159, 0.00005))),
  room: collection(polygon("room", {}, square(171.86193, -42.11607, 0.00024))),
};
