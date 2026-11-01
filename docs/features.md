# Features

What Button NZ does today, where each feature lives, and what it deliberately
doesn't do. Every feature here is built, tested and running at
https://button.nz. How they fit together on the page is in
[information-architecture.md](information-architecture.md); who uses them is in
[user-journeys.md](user-journeys.md).

## The site

| Feature | What it does | Where |
|---|---|---|
| **A real, verified site** | 35 Victory Street, Reefton: four sections on one title, with the parcels, the 1 m LiDAR DEM and DSM, and the 7.5 cm aerial photo pinned to exact tiles. Each dataset records its source, licence and attribution, and its capture dates where they are known | `data/demo-site/`, `button_nz.demo_site` |
| **Site plan** | The parcels drawn north up over the aerial photo, with the surveyed features and a key | `SitePanel.tsx`, `api/aerial.py` |
| **Sources and open items** | Every dataset's licence, its capture dates where recorded (the parcels have none), and what is still to confirm, on the page | `SitePanel.tsx` |

## The survey

| Feature | What it does | Where |
|---|---|---|
| **SAM 3.1 survey** | Segments the aerial photo one concept at a time (building, shed, tree, hedge, garden bed, driveway, path, car). Each mask becomes a polygon on the national grid | `perception/sam.py`, `perception/survey.py` |
| **Checked against the LiDAR** | Where the LiDAR can see it, each feature's height is read from the nDSM, and its status says whether the photo and the LiDAR agree: "agrees", "conflict" (the owner decides), "unlabelled" (raised ground no label covers), "transient" (a parked car, not part of the site) or "unchecked" (no rule for the concept, or too small for 1 m cells, so no height). Nothing is guessed | `perception/features.py`, `perception/survey.py` |
| **The owner decides** | Each feature is an existing building, an area to keep clear, or nothing to the design. Nothing SAM finds constrains a design until a person decides | `FeaturesPanel.tsx`, `api/features.py` |
| **Buildings complete** | The owner says every building is listed. Until then, separation never passes: a design within 2 m of a confirmed building still fails, and otherwise it is "unknown" | `FeaturesPanel.tsx`, `perception/confirm.py` |
| **A fixed survey** | A public server can fix the survey as the owner decided it: shown with who decided, and closed to changes | `serve --survey-decided-by` |

## Designing

| Feature | What it does | Where |
|---|---|---|
| **A brief in plain words** | "A small one-bedroom studio that gets the afternoon sun", up to 4,000 characters | `DesignPanel.tsx` |
| **Muse Spark designs in Blender** | Muse Spark 1.3 writes a complete Blender Python script as a tool call, to a contract: one Dwelling mesh, built on the terrain | `agent/loop.py`, `agent/prompt.py` |
| **LiDAR views on request** | Before each attempt, Muse may ask for up to four views: hillshade, contours, slope, height maps, cross-sections between two points, or elevations over an area. They don't count as attempts | `agent/observe.py`, `lidar/` |
| **Sandboxed Blender** | The script runs in headless Blender inside a bubblewrap sandbox: no network, no keys, read-only system files, capped memory, processes and scratch space | `blender_worker/sandbox.py` |
| **A trusted measuring pass** | A second Blender pass reloads only the model's objects, checks the contract, measures every rendered triangle, and exports the GLB and a Cycles render | `blender_worker/` |
| **Repair from feedback** | A failed check goes back to Muse as feedback, with the render when the attempt produced one, for up to three attempts | `agent/loop.py` |
| **Live progress** | The page follows the design as each attempt finishes | `useDesignChain.ts` |
| **3D view** | The accepted design, or any attempt that produced a model, in 3D on the site's terrain | `ModelViewer.tsx` |

## Checking

| Feature | What it does | Where |
|---|---|---|
| **An independent evaluator** | Ordinary code measures the geometry. Two inputs are the model's. Its stated internal floor area is bounded by the walls (the inside can't exceed the outside, and no realistic wall is over 0.6 m thick): it decides only between those bounds, and an area only unusually thick walls explain is "unknown". Its storey count can only fail a design, never pass one. A failed check can't be argued away | `evaluation/` |
| **The exemption's measurable rules** | Schedule 1A of the Building Act, as MBIE's guidance quotes it. Each check is pass, fail or unknown, with its measurement and rule (the page shows the verdict and a plain detail; the rule and every measurement are in the attempt's trace): on the title; 2 m from the title boundary; internal section lines (a footprint across one fails; one within 2 m without crossing is unknown, since nothing yet records whether they are legal boundaries); 2 m from confirmed buildings; floor area within 70 m²; one storey; height within 4 m of the floor; floor within 1 m of the ground; keep-clear areas | `evaluation/checks.py` |
| **Honest unknowns** | What the data can't decide is "unknown", never a pass. A design otherwise clear of confirmed buildings while the list isn't confirmed complete; a floor within 1 m of the lowest ground but below the ground elsewhere; a footprint within 2 m of a line between sections without crossing it. Each of these checks still fails outright when the data does decide it | `evaluation/checks.py` |
| **Recorded against what it was checked on** | Each design records the survey's id and the decisions it was checked against, as they were when it ran | `api/jobs.py` |

## Changing a design

| Feature | What it does | Where |
|---|---|---|
| **Revise in plain words** | "Move it 3 m further from the street." Muse starts from the accepted script; the evaluator checks the result again | `Revisions.tsx`, `api/jobs.py` |
| **History, before and after** | Every step of the chain is listed; any step can be shown beside the one it changed | `Revisions.tsx` |
| **Shareable links** | `?design=<id>` opens a design and the designs it revises; the address bar follows the design on show | `useDesignChain.ts` |

## The AI visual

| Feature | What it does | Where |
|---|---|---|
| **Muse Image illustration** | Muse Image 1.0 turns the trusted render into a photograph of the same scene | `perception/visual.py` |
| **Checked before it is shown** | SAM 3.1 finds the house in the illustration. It is shown only if it overlaps the design's silhouette from the same camera (IoU ≥ 0.6), labelled AI-illustrated | `perception/visual.py` |

## Real prefabs

| Feature | What it does | Where |
|---|---|---|
| **A sourced catalogue** | 17 New Zealand prefab products of up to 70 m² from 6 suppliers, from their own pages: outside footprint, area and its basis, rooms, price (or "not published"), exclusions, West Coast delivery, sources | `data/catalogue/products.json`, `catalogue/products.py` |
| **Which prefabs fit** | Products whose published footprint fits inside an accepted design's walls, largest first. Products whose figures aren't labelled are listed as unchecked, never as fitting | `catalogue/fit.py`, `ProductsPanel.tsx` |
| **Place a prefab** | "Place it on the site" designs again with the product's footprint as the walls. The evaluator checks the walls are that footprint, by area, to 0.10 m, before every other check. A product whose figures only bound a stepped plan (Lockwood Ara) can't be placed | `evaluation/checks.py` (`product_footprint`), `api/app.py` |
| **Next steps** | What the exemption asks of the owner next: a PIM from Buller District Council, licensed people, a ground test, and records to the council within 20 working days | `ProductsPanel.tsx`, [suppliers.md](suppliers.md) |

## Town scale

| Feature | What it does | Where |
|---|---|---|
| **The town screen** | Runs the same fit over all 1,320 residential sections in Reefton, each on its own, 2 m from its boundaries and buildings. 762 (58%) have room for a real prefab with 0.6 m eaves, on LINZ's 2015–16 outlines; 409 (31%) also clear of everything over 2 m on the LiDAR. It's a screen, not a verdict | `town/`, `bench/town_screen.py`, [report](results/town-screen/report.md) |

## Serving it

| Feature | What it does | Where |
|---|---|---|
| **Deployed** | The API, the web app and a Cloudflare tunnel run as systemd services on the GPU machine; nothing listens beyond 127.0.0.1 | `scripts/deploy/`, [deploy.md](deploy.md) |
| **Daily cap** | At most 30 design runs (originals, revisions and placements) start in any 24 hours; one past it is refused with when the next frees up | `api/limits.py` |
| **Optional access code** | A code can gate every page and API request. `install.sh` generates one; button.nz runs with `BUTTON_ACCESS_CODE` emptied, so it is open to anyone | `apps/web/proxy.ts`, `lib/access.ts` |
| **Smoke test** | Checks a code-gated URL as a visitor reaches it: the gate, the page, the site and a fixed survey (an open server is #84) | `scripts/deploy/check.sh` |

## Evidence

| Feature | What it does | Where |
|---|---|---|
| **Experiments from live runs** | Experiment A (does Muse understand LiDAR: 49% from the photo alone, 83% choosing its own views) and C (what feedback buys: 56% accepted one shot, 100% with the evaluator), and the design-model comparison | `bench/`, [results](results/README.md) |
| **Sample artifacts** | Packs a design and the designs it revises (pass the latest revision), with the survey they were checked against and every verdict, and refuses partial or inconsistent samples | `button_nz.sample` |
| **Demo recording** | Records the live app in a headless browser and cuts it, with the speed shown wherever it's sped up | `scripts/demo/` |

## What it doesn't do

- **It isn't a building consent or a compliance decision.** It checks the
  exemption's measurable siting and size conditions. It doesn't check
  hazards, the district plan, services, structure or cladding weights.
- **One site.** Only the demo site is wired up. The town screen shows the
  same code working town-wide, but its sections aren't designable in the app.
- **No accounts.** One shared server: designs are open to anyone with the
  link, and the survey is the owner's.
- **No supplier quotes.** Prices are only what suppliers publish; ten of the
  17 publish none.
- **Eaves aren't the supplier's.** A placed prefab is checked with the eaves
  Muse draws; suppliers mostly don't publish theirs.
