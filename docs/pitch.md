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

An owner opens their property and, in one session:

1. **Sees what is there.** SAM 3.1 picks out the sheds, trees and garden beds
   on the aerial photo, and each is checked against the LiDAR heights. Where
   they disagree, the owner is asked, not guessed for.
2. **Describes what they want**, in their own words: "a small one-bedroom
   studio that gets the afternoon sun."
3. **Gets a checked concept.** Muse Spark looks at the site through LiDAR
   views it chooses itself (contours, slope, cross-sections, exact
   elevations), then designs the dwelling by writing a Blender program. Blender
   runs it in a sandbox. An independent evaluator measures the geometry
   against the exemption's rules. If a check fails, Muse sees the
   measurements and its own render, and fixes the design.
4. **Changes it in plain words**, "move it 3 m further from the street", and
   every revision is checked again.
5. **Sees which real prefabs fit**, with prices where published, what they
   leave out, and who to call next.

## How we use Meta's models

- **Muse Spark 1.3** is the design agent. It works in a tool loop:
  - it asks for LiDAR views of the site;
  - it writes a complete Blender Python script as a tool call;
  - it reads the evaluator's verdict and its own render;
  - it repairs the design, or revises an accepted one in plain words.
- **SAM 3.1** surveys the site from the aerial photo, one concept at a time.
  It also checks each AI illustration: the house it finds must overlap the
  design's silhouette.
- **Muse Image 1.0** turns the trusted render into a photograph-like
  illustration, shown only when SAM's check passes, and labelled
  AI-illustrated.
- **Muse Wonder 1.0** was compared with Spark as the design agent. Both had
  every run accepted; Spark was faster, so it designs.

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
  code was run over all 1,320 residential sections in Reefton, each checked
  on its own, 2 m from its boundaries and from every building. With 0.6 m
  eaves allowed for, a real prefab fits on:
  - **762 (58%)**, judged against LINZ's 2015–16 building outlines;
  - **409 (31%)**, also clear of everything over 2 m on the 2020–24 LiDAR,
    trees included: room without removing anything that tall. Lower things,
    and anything added since the LiDAR, aren't seen.

  Of the 986 that already have a building on them, 488 and 258. It's a
  screen, not a verdict: hazards, slope, the district plan and services
  aren't checked.

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
- **Web:** Next.js. The 3D model, every check with its measurement and rule,
  the revision history, and the prefab panel.

## Honest limits

- It checks the exemption's measurable conditions, not a building consent,
  the district plan, hazards or services.
- The lines between sections on one title are reported as "unknown" until
  confirmed as legal boundaries.
- Prefab fits use each product's stated dimensions; most suppliers don't
  publish eaves, so a fit isn't a setback verdict for that product.

## What's next

- **More of the country:** wherever LiDAR and parcel data exist, the pipeline
  already works.
- **Designing to a chosen prefab's footprint**, so Muse places a real product
  on the site.
- **A handover pack** for the designer and the council.

## Links

- Source: https://github.com/gardner/button-nz (GNU GPL)
- Live demo: **pending** (docs/deploy.md: a public hostname)
- Video: **pending** (the final take)
