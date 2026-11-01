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
  id: "35-victory-street-reefton",
  address: "35 Victory Street, Reefton",
  status: "building",
  step: "terrain",
  error: null,
};

/** GET /sites/{id} once it is ready (#88's `_view`, as tests/test_api_sites.py
 * asserts it): GET /site's fields at the top level, its NZTM point renamed
 * `address_nztm` so `address` stays the text, with lon/lat bounds and the
 * aerial. */
export const SITE_READY = {
  name: "35 Victory Street, Reefton",
  title: "354613",
  valuation_number: null,
  crs: "EPSG:2193",
  address_nztm: [1505941.6, 5336793.7],
  extent: [1505926.13, 5336777.48, 1505969.74, 5336822.22],
  parcels: { type: "FeatureCollection", features: [] },
  sources: {},
  open_items: [],
  id: "35-victory-street-reefton",
  address: "35 Victory Street, Reefton",
  status: "ready",
  step: null,
  error: null,
  bounds: [171.8619, -42.1161, 171.8625, -42.1155],
  aerial: null,
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
  missing: { ids: [], reason: "not in LINZ's NZ Primary Parcels" },
  buildings: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: 11,
        properties: { base_m: null, height_m: null }, // beyond the LiDAR
        geometry: {
          type: "Polygon",
          coordinates: square(171.8603, -42.1159, 0.00002),
        },
      },
      {
        type: "Feature",
        id: 10,
        properties: { base_m: 0, height_m: 6.5 },
        geometry: {
          type: "Polygon",
          coordinates: square(171.8601, -42.1159, 0.00005),
        },
      },
    ],
  },
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

/** A feature as #88's `sites.layers.collection` writes it: its id in its
 * properties, none at the top level. */
function unnamed(properties: object, coordinates: unknown) {
  return {
    type: "Feature",
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
  buildings: collection(
    polygon(
      25,
      { id: 25, height_m: 6.2, base_m: 2.2 },
      square(171.8623, -42.1158, 0.00006),
    ),
    polygon(
      26,
      { id: 26, height_m: null, base_m: null },
      square(171.8625, -42.1158, 0.00002),
    ),
  ),
  canopy: collection(
    polygon(
      "c0",
      { base_m: 1.2, height_m: 9.3 },
      square(171.8618, -42.1157, 0.00004),
    ),
  ),
  features: collection(
    unnamed(
      {
        id: "1",
        concept: "shed",
        status: "agrees",
        decision: "ignore",
        height_m: null,
      },
      square(171.862, -42.116, 0.00004),
    ),
    unnamed(
      {
        id: "3",
        concept: "tree",
        status: "agrees",
        decision: "keep_clear",
        height_m: 7.2,
      },
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

/** Checks per attempt, as GET /designs/{id} sends them (#86). */
export const CHECKS = [
  {
    name: "title_boundary_setback",
    status: "pass",
    detail: "3.20 m from the title boundary; at least 2 m required.",
    measured: { value: 3.2, minimum: 2 },
    rule: "Building Act 2004, Schedule 1A",
  },
  {
    name: "building_separation",
    status: "unknown",
    detail: "No existing buildings are confirmed by the owner.",
    measured: {},
    rule: "Building Act 2004, Schedule 1A",
  },
  {
    name: "floor_area",
    status: "fail",
    detail: "The footprint is 72.0 m²: over 70.",
    measured: { footprint_area_m2: 72, maximum: 70 },
    rule: "Building Act 2004, Schedule 1A",
  },
];

/** GET /designs/{id}/map */
export const DESIGN_MAP = {
  outline: collection(
    polygon(
      "outline",
      { base_m: 0.3, height_m: 3.9 },
      square(171.862, -42.1159, 0.00009),
    ),
  ),
  walls: collection(
    polygon(
      "walls",
      { base_m: 0.3, height_m: 3.9 },
      square(171.86201, -42.11589, 0.00007),
    ),
  ),
  distances: collection({
    type: "Feature",
    id: "d1",
    properties: { check: "title_boundary_setback", metres: 3.2, required: 2 },
    geometry: {
      type: "LineString",
      coordinates: [
        [171.862, -42.1159],
        [171.86196, -42.11593],
      ],
    },
  }),
};
