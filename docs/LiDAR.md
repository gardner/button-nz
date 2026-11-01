# LiDAR: which data Button NZ uses

## Buller District: one dataset, the West Coast survey as LINZ publishes it

For Reefton and the rest of Buller District, Button NZ uses **West Coast
LiDAR 1m DEM (2020–2024)** and **West Coast LiDAR 1m DSM (2020–2024)**. They
are one survey, described in two ways:

- **West Coast Regional Council** commissioned the survey and licenses it
  (CC BY 4.0).
- **Aerial Surveys** flew and produced it, between May 2020 and July 2024.
- **Toitū Te Whenua LINZ** processes and hosts it in the national elevation
  series. This is where Button NZ reads it from: LINZ's public `nz-elevation`
  bucket, as cloud-optimised GeoTIFFs
  (`west-coast/west-coast_2020-2022/dem_1m` and `.../dsm_1m`).

So "the West Coast LiDAR" and "the LINZ LiDAR" are the same data for Buller.
The collection's own metadata names all three roles: LINZ is host and
processor, Aerial Surveys the producer, and West Coast Regional Council the
licensor. The attribution Button NZ shows matches it: "Toitū Te Whenua Land
Information New Zealand, Aerial Surveys, West Coast Regional Council".

LINZ's catalogue (checked 1 November 2026) holds no other collection for the
West Coast region. Its other "west coast" entry,
`waikato/west-coast-and-hauraki-plains_2015`, is the Waikato's west coast,
not ours.

What other copies might exist, not checked here:
- the council, or a survey portal such as OpenTopography, may also hold the
  raw point clouds (LAZ);
- older, local surveys may predate the 2020–24 capture.

Button NZ uses neither. It reads only LINZ's 1 m ground and surface models,
which are derived from those point clouds.

## What Button NZ reads from it

- **DEM (bare ground)** and **DSM (first surface: roofs, trees)**, 1 m cells,
  NZVD2016 heights.
- **nDSM = DSM − DEM:** what stands above the ground. It gives:
  - building and tree heights;
  - the survey's height checks;
  - the canopy;
  - the town screen's "clear today" count.
- **Muse's LiDAR views:** hillshade, contours, slope, cross-sections and
  exact elevations, all rendered from the DEM and nDSM.
- **The evaluator's ground:** floor level and earthworks.

## Everywhere else

A site built for any other address uses whichever LINZ 1 m DEM and DSM
collections cover its point, the newest capture first (`sites/stac.py`). For
example, a Petone address uses "Wellington – Hutt City LiDAR 1m DEM/DSM
(2025)". Where LINZ has no 1 m DEM and DSM, the site is reported as having no
LiDAR. Nothing is substituted.
