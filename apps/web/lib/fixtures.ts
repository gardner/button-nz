/** API responses shared by the tests. */

export const JOB = {
  id: "abc123",
  brief: "A small studio.",
  allow_observations: true,
  status: "done",
  created_at: "2026-10-28T09:00:00Z",
  started_at: "2026-10-28T09:00:01Z",
  finished_at: "2026-10-28T09:03:00Z",
  error: null,
  accepted_attempt: 2,
  parent_id: null, // an original design, not a revision of one
  instruction: null,
  illustrating: false, // no AI visual still to come
  attempts: [
    {
      number: 1,
      status: "fail",
      feedback: "title_boundary_setback: fail. 0.50 m from the boundary.",
      observations: ["render_contours"],
      files: { "design.png": "/designs/abc123/attempts/1/design.png" },
    },
  ],
};

function square(x: number, y: number, size: number): number[][] {
  return [
    [x, y],
    [x + size, y],
    [x + size, y + size],
    [x, y + size],
    [x, y],
  ];
}

/** GET /site/features: a decided shed, a tree the LiDAR disagrees with (in
 * two pieces) and raised ground no concept labelled. */
export const SURVEY = {
  type: "FeatureCollection",
  model: "sam-3.1", // survey metadata the app doesn't read
  crs: "EPSG:2193",
  survey_id: "s1",
  buildings_complete: false,
  features: [
    {
      type: "Feature",
      id: "1",
      properties: {
        concept: "shed",
        score: 0.91,
        area_m2: 12.25,
        max_height_m: 2.6,
        status: "agrees",
        note: "The LiDAR shows 4% of it under 0.5 m.",
        decision: "building",
      },
      geometry: { type: "Polygon", coordinates: [square(1002, 2002, 3.5)] },
    },
    {
      type: "Feature",
      id: "2",
      properties: {
        concept: "tree",
        score: 0.64,
        area_m2: 8,
        max_height_m: 0.3,
        status: "conflict",
        note: "The LiDAR shows 90% of it under 0.5 m.",
        decision: null,
      },
      geometry: {
        type: "MultiPolygon",
        coordinates: [[square(1010, 2010, 2)], [square(1014, 2010, 2)]],
      },
    },
    {
      type: "Feature",
      id: "3",
      properties: {
        concept: "unlabelled",
        score: null,
        area_m2: 5,
        max_height_m: null,
        status: "unlabelled",
        note: "The LiDAR shows 5 m² standing up here; no mask labels it.",
        decision: null,
      },
      geometry: { type: "Polygon", coordinates: [square(1004, 2014, 2)] },
    },
  ],
};

/** GET /designs/abc123/products: one product that fits, one unchecked. */
export const PRODUCTS = {
  footprint_m2: 65.0,
  basis:
    "A product fits if its published outside footprint lies inside the accepted design's walls.",
  fits: [
    {
      id: "airhome-vista",
      supplier: "AirHome",
      model: "Vista",
      url: "https://www.airhome.co.nz/airhome-vista/",
      type: "transportable",
      length_m: 12.2,
      width_m: 4.0,
      dimensions_labelled: true,
      floor_area_m2: 48,
      area_basis: "not stated",
      bedrooms: 2,
      bathrooms: 1,
      price_nzd: 190000,
      price_basis: "incl GST; construction only",
      excludes: "decking, landscaping, delivery, installation and any other costs",
      west_coast: "Delivers anywhere in NZ (Christchurch factory); West Coast not named",
      sources: [
        "https://www.airhome.co.nz/airhome-vista/",
        "https://www.airhome.co.nz/faq/",
      ],
    },
    {
      id: "south-peak-nile",
      supplier: "South Peak Homes",
      model: "Nile",
      url: "https://southpeakhomes.co.nz/floor-plans/nile/",
      type: "transportable",
      length_m: 12.0,
      width_m: 3.5,
      dimensions_labelled: true,
      floor_area_m2: 42,
      area_basis: "not stated",
      bedrooms: 2,
      bathrooms: 1,
      price_nzd: null,
      price_basis: "price on application; prices incl GST",
      excludes: "not listed",
      west_coast: "West Coast is on its region list",
      sources: ["https://southpeakhomes.co.nz/floor-plans/nile/"],
    },
  ],
  unchecked: [
    {
      id: "keith-hay-nook-60",
      supplier: "Keith Hay Homes",
      model: "Nook 60",
      url: "https://www.keithhayhomes.co.nz/our-plans/minor-dwellings/nook-60.html",
      type: "transportable",
      length_m: 9.52,
      width_m: 6.6,
      dimensions_labelled: false,
      floor_area_m2: 60,
      area_basis: "not stated",
      bedrooms: 2,
      bathrooms: 1,
      price_nzd: null,
      price_basis: "not published",
      excludes: "delivery and foundations",
      west_coast: "not stated",
      sources: [
        "https://www.keithhayhomes.co.nz/our-plans/minor-dwellings/nook-60.html",
      ],
    },
  ],
};
