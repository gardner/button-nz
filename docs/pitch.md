# Button NZ: submission text

Draft text for the submission form, Indie track, theme "Build for Your World".
Every number links to the report it comes from. Items marked **pending** wait
on something not yet done; fill them in only from what is actually produced.

## Name and tagline

**Button NZ**: unlock the housing hiding in your backyard.

## The problem

New Zealand lets an owner build a detached granny flat of up to 70 m² without
a building consent, if it meets the conditions of Schedule 1A of the Building
Act: 2 m from boundaries and other residential buildings, one storey, at most
4 m high, and more. But an owner can't tell whether their section qualifies,
or what would fit on it, without first paying a designer or surveyor. Most
never find out.

The answer is already in public data: survey-accurate parcel boundaries, 1 m
LiDAR of the ground and everything on it, and 7.5 cm aerial photographs.

## What it does

Anyone opens https://button.nz and, in one session:

1. **Finds their property by its address** (or, in Reefton, taps its section
   on the map, even one with no address), anywhere in New Zealand where
   LINZ has 1 m LiDAR, a recent aerial photo (0.3 m or finer) and the title's
   parcels. The site is built live, once, from open data; where one of those
   is missing, it says which rather than guessing:
   - the title's parcels and the neighbouring building outlines;
   - the newest LiDAR ground and surface models that cover it;
   - the regional aerial photo.

   The landing map shows the idea at town scale: every residential section in
   Reefton, coloured by whether a real prefab fits.
2. **Sees what is there.** SAM 3.1 picks out the buildings, sheds and trees
   on the aerial photo, and each is checked against the LiDAR heights. Where
   they disagree, the owner is asked, not guessed for. The rules are drawn on
   the land: the 2 m setback band, and halos around buildings.
3. **Describes what they want**, in their own words: "a small one-bedroom
   studio that gets the afternoon sun."
4. **Gets a checked concept.**
   - Muse Spark looks at the site through LiDAR views it chooses itself
     (contours, slope, cross-sections, exact elevations).
   - It then designs the dwelling by writing a Blender program, which runs in
     a sandbox.
   - An independent evaluator measures the geometry against the exemption's
     rules. If a check fails, Muse sees the measurements and its own render,
     and fixes the design.
   - The accepted design stands in 3D on the map, among the neighbours and
     trees the LiDAR measured, with each check as a ✓/✗/? badge and the
     distances labelled on the land.
5. **Changes it in plain words**, "move it 3 m further from the street", and
   every revision is checked again.
6. **Places a real prefab.** The panel shows which real New Zealand prefabs
   fit, with published prices and what they leave out. "Place it on the
   site" has Muse design again to that product's exact footprint, and the
   evaluator checks the walls really are that footprint. Live, the AirHome
   Vista was accepted on its first attempt at 12.2 × 4.0 m.

## How we use Meta's models

- **Muse Spark 1.3** is the design agent. It works in a tool loop:
  - it asks for LiDAR views of the site;
  - it writes a complete Blender Python script as a tool call;
  - it reads the evaluator's verdict and its own render;
  - it repairs the design, or revises an accepted one in plain words.
- **SAM 3.1** surveys the site from the aerial photo, one concept at a time.
  It also checks each AI illustration: the house it finds must overlap the
  design's silhouette.
- **Muse Image 1.0** turns a close-up of the trusted render, three times
  the dwelling's size, into a photograph-like illustration, shown only when
  SAM's check passes, and labelled AI-illustrated.
- **Muse Wonder 1.0** was compared with Spark as the design agent. Both had
  every run accepted; Spark was faster, so it designs.
- **SAM 3D Objects** (an experiment, not in the app): can it rebuild a real
  house from our aerial photo, and does the measured LiDAR, given in place of
  its own depth estimate, make that accurate? No: the LiDAR fixes its
  placement and scale, not its shape. Its roofs are 0.9–1.5 m from held-out
  LiDAR, against 7–11 cm for Roofer, a conventional reconstruction from the
  same points, so it stays out of the app
  ([write-up](experiments/sam3d-lidar/README.md)).

## What we measured

From live runs on the demo site ([docs/results](results/README.md)):

- **Feedback makes designs pass.** On the surveyed site, 9 runs per condition:
  - one shot: 56% accepted;
  - with the evaluator's verdict and render fed back: 100%, every failed
    first attempt repaired.
- **Choosing its own views helps Muse read terrain.** On 47 questions with
  answers computed from the LiDAR:
  - the aerial photo alone: 49% correct;
  - every fixed map: 66%;
  - the agent choosing its own views and querying elevations: 83%.
- **Town scale** ([report](results/town-screen/report.md)): the same fit
  code was run over every residential property in Reefton: 959 titles,
  made of 1,320 parcels. Each parcel is checked on its own, 2 m from its
  boundaries and from every building; a property has room if any of its
  parcels does. With 0.6 m eaves allowed for, a real prefab fits on:
  - **622 properties (65%)**, judged against LINZ's 2015–16 building
    outlines;
  - **326 (34%)**, also clear of everything over 2 m on the 2020–24 LiDAR,
    trees included: room without removing anything that tall. Lower things,
    and anything added since the LiDAR, aren't seen.

  Of the 745 properties with a LINZ building outline, 439 and 235: room for
  a flat in the backyard. It's a screen, not a verdict: hazards, slope, the
  district plan and services aren't checked.
- **On real sections, not just the demo** ([results](results/README.md)):
  6 Reefton sections built from their addresses and designed on the live
  app (a seventh had no address), before and after Muse was told which title edges face which road and
  where a plain rectangle fits. Accepted on the first attempt: 5 of 6, then
  6 of 6. "As far from the street as the rules allow" went from 2.34 m to
  21.15 m at 7 Smith Street and from 3.67 m to 24.95 m at 81 Main Street.
  One design per brief and site: an indication, not proof.
- **The AI visual is checked, and sometimes refused.** On 12 accepted
  designs, Muse Image's picture of the whole render passed SAM 3.1's
  silhouette check 7 to 8 times in 12 across runs. Illustrating a close-up
  of the dwelling instead passed 10 of 12, in one run made straight after
  one of the whole-render runs. A refused picture is never shown.
- **What it could mean** ([report](results/impact/report.md)): if a quarter
  of the 439 backyards with room added a flat, Reefton would have 109 more
  homes, 18% more than its 603 private dwellings in the 2023 Census,
  housing 109 to 212 people. 42% of Reefton's households (with a stated size) are one person:
  small homes fit. That's a scenario, not a forecast.

## How it's built

- **Data:** LINZ open data (CC BY 4.0) and Buller District Council's public
  parcel and zone layers (no licence stated), with sources, licences and
  capture dates recorded for the site.
- **Pipeline:** Python with FastAPI, shapely and rasterio; Blender 5 (Cycles,
  OptiX) on an RTX 5090.
- **Sandbox:** model-written scripts run in a bubblewrap sandbox: no network,
  no keys, read-only system files, capped memory and processes.
- **Evaluator:** ordinary code that measures the triangles actually rendered.
  A failed check stays failed whatever the model says. A check it can't
  decide is "unknown", never a pass.
- **Web:** Next.js with MapLibre:
  - LINZ's aerial basemap, with the rules and the survey drawn on it;
  - a 2D/3D view whose buildings and trees stand on the LiDAR's heights;
  - the design's checks, revisions and prefabs beside the map.
- **Any address:** LINZ's address register, NZ Primary Parcels and building
  outlines, and its national elevation catalogue (the newest 1 m DEM and DSM
  covering the point). Each site is built once and cached.

## Honest limits

- It checks the exemption's measurable conditions, not a building consent,
  the district plan, hazards or services.
- The lines between sections on one title are reported as "unknown" until
  confirmed as legal boundaries.
- Prefab fits use each product's stated dimensions; most suppliers don't
  publish eaves, so a fit isn't a setback verdict for that product.
- The AI visual is refused when it doesn't match the design's silhouette,
  which happened on 2 of 12 designs in the latest run. It shows the
  dwelling close up, not the whole site; the 3D view shows the site.

## What's next

- **More rules:** the district plan's rules for each zone, and the natural
  hazards in the project information memorandum (PIM) a council issues.
  Today it checks only the building exemption's measurable conditions.
- **Supplier quotes** for the ten catalogue products with no published
  price, and more suppliers.
- **A handover pack** for the designer and the council: the site, the
  accepted design, its checks and the open questions.

## Links

- Source: https://github.com/gardner/button-nz (GNU GPL)
- Live demo: https://button.nz (open; at most 30 design runs a day)
- Video: **pending** (the final take)
