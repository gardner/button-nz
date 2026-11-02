# Information architecture

How Button NZ's content is organised: the one page people use, the data
behind it, the API that serves it, and the files a design run leaves. For what
each part does, see [features.md](features.md); for who uses it and how, see
[user-journeys.md](user-journeys.md).

## The page

Button NZ is one page (`apps/web/app/page.tsx`, the `Explore` component),
served at https://button.nz: a full-screen aerial map with a panel over its
left and the journey's steps across the top. On a phone the panel spans the
width and the map frames what it shows below it.

```
Button NZ                  Find · Survey · Design · Check · Prefab        2D | 3D
├── The map (BaseMap): LINZ's aerial basemap
│   ├── Reefton's sections, coloured by the town screen (clear · outlines · none);
│   │   in 3D the town's buildings stand at their LiDAR heights
│   └── Once a site is ready (SiteLayers, DesignLayers):
│       ├── Parcels, the 2 m setback band, 2 m halos round confirmed buildings,
│       │   keep-clear areas and the room left for a dwelling
│       ├── The surveyed features, coloured by decision; a tap picks one
│       ├── The accepted design: its outline, walls and each measured distance
│       │   (DistanceLabels)
│       └── In 3D: the site's buildings and trees, and the design, standing at their
│           heights; on acceptance the camera flies round the design (Orbit)
└── The panel (SidePanel)
    ├── Unlock the housing hiding in your backyard (until a site is chosen)
    ├── Address search (SearchBox): any New Zealand address, from LINZ
    ├── The town's headline (TownOverview): how many sections have room
    ├── Building the site (BuildProgress): parcels, terrain, aerial, survey
    └── A ready site (ReadySite)
        ├── Your site: its address, and anything its map couldn't show
        ├── What's on the site? (SurveyPanel): one chip per surveyed feature, the
        │   picked one's three decisions, and "Every building on the site is listed"
        ├── What would you like to build? (DesignDock): the brief, examples, the
        │   history, each attempt (AttemptRow: verdict, a badge per check, the LiDAR
        │   views asked for), and Change this design
        ├── Which real prefabs fit? (PrefabSection, PrefabPanel): each with its
        │   size, price, area basis and West Coast delivery, shown on the map while
        │   pointed at, and "Place it on the site"; then the next steps (NextSteps)
        └── The accepted design's hero (HeroMedia): 3D model, AI visual, before/after
```

### Addresses

| Address | What it shows |
|---|---|
| `/` | Reefton's sections and the address search |
| `/?site=<id>` | That site, built or being built |
| `/?site=<id>&design=<id>` | That design on its site, after the designs it revises. The address bar follows the design on show, so any step can be shared |
| `/?design=<id>` | Links from before sites: opens the design's own site, then the design |
| `/explore` | Redirects to `/`, keeping the query |
| `/?code=<code>` | Only when the server has an access code: sets the access cookie and drops the code from the address |

## The content

Each object, what it holds, and where it comes from.

| Object | Holds | Source | Kept in |
|---|---|---|---|
| **Site** | Name, title, parcels, extent, rasters and vectors with licences and, where recorded, capture dates, open items | LINZ open data (CC BY 4.0) and Buller District Council's public parcels (no licence stated), pinned and verified | `data/demo-site/site.json`, `parcels.geojson` |
| **Survey** | What SAM 3.1 found on the aerial photo, plus raised ground on the LiDAR that no label covers (concept "unlabelled", no score). Each is a polygon (SAM's mask isn't kept) with its concept, score, area, height where the LiDAR has one, status and note | `python -m button_nz.perception.survey` | `DATA/survey.geojson` |
| **Decision** | Building, keep clear or ignore, per feature; whether every building is listed | The owner, in the app | `DATA/button.db` (decisions, surveys) |
| **Design** (job) | Brief, whether it may observe, status, timestamps, accepted attempt, parent and instruction (a revision), placed product | The owner's brief or change | `DATA/button.db` (jobs) |
| **Attempt** | Verdict, feedback, LiDAR views asked for, and, where those steps completed, the model's script and its measured result | The design loop | `DATA/button.db` (attempts), `DATA/runs/<job>/attempt-<n>/` |
| **Check** | Name, pass, fail or unknown, a plain detail, measurements, the rule it comes from. The page shows the name, verdict and detail; the measurements and rule are in the trace | The evaluator (`button_nz.evaluation`) | Each attempt's `attempt.json` |
| **Product** | Supplier, model, outside footprint, area and its basis, rooms, price or null, exclusions, West Coast note, sources; whether it can be placed | Suppliers' own pages | `data/catalogue/products.json` |
| **Placed product** | The product a design places, as the catalogue gave it then | The owner's "Place it on the site" | `DATA/button.db` (jobs.product) |
| **Survey record** | The survey's id and the decisions a design was checked against (not the survey's features themselves: a replaced survey can't be recovered from it) | The worker, as each design runs | `DATA/runs/<job>/survey.json` |

### Vocabulary

The page and the docs use these words consistently:

| Word | Means |
|---|---|
| Section | One parcel of land. A title can hold several |
| Survey | What SAM 3.1 found on the photo, and raised ground only the LiDAR saw, before anyone decides what it is |
| Keep clear | An area no design may build on (a tree, a garden) |
| Brief | What the owner wants, in their own words |
| Attempt | One turn of the design loop: Muse writes a script, Blender builds it, the pass measures it. It can end at any of those steps |
| Accepted | No check failed on the attempt. An "unknown" check doesn't stop acceptance, but is shown |
| Revision | A change to an accepted design, in plain words |
| Fits | A product's published outside footprint lies inside the accepted design's walls |
| Placed | A design built to a product's footprint and checked to be it |

## The API

The web app reaches the API through its own `/api` path, so the browser stays
on one origin. Everything below is relative to `/api`.

```
/site                                    GET   the site: parcels, sources, open items
/site/aerial.png                         GET   the aerial photo, cut to the site
/site/features                           GET   the survey with each decision
/site/features/{id}                      PUT   decide a feature (403 if the survey is fixed)
/site/survey                             PUT   every building is listed (403 if fixed)
/designs                                 POST  start a design; product_id places a prefab
/designs/{id}                            GET   status, attempts, accepted attempt, product
/designs/{id}/revisions                  POST  change an accepted design
/designs/{id}/attempts/{n}/{file}        GET   design.glb, design.png, observation-k.png,
                                               visual.png, visual.json only
/designs/{id}/products                   GET   the prefabs that fit an accepted design
/town/{slug}                             GET   a town's screen as a map layer (reefton)
/tiles/aerial/{z}/{x}/{y}.webp           GET   LINZ's aerial basemap, through the server's key
```

The town layer and the aerial tiles are served for the map-first UI (#86);
nothing on today's page uses them yet. A public server adds two limits: a daily cap on design runs (429 past it), and
a survey fixed as the owner decided it (403 on changes). See
[deploy.md](deploy.md).

## A design run's files

Each design keeps its files under `DATA/runs/<job>/`:

```
survey.json                 the survey's id and the decisions it was checked against
design.json                 the run's summary, once the design loop finishes
attempt-<n>/                each file below exists only if its step ran: an attempt
                            with no script keeps just its trace and observations, and
                            one whose script failed has nothing from the later passes
  attempt.json              the agent's trace: observations, script, verdict, feedback
  observation-<k>.png       the image-producing LiDAR views the model asked for
  scene.json                the georeferenced site scene
  design.py                 the model's Blender script
  script/design.blend       the Blender file it saved
  measurements.json         what the trusted pass measured
  design.glb, design.png    the measured design, exported and rendered
  dwelling-mask.png         its silhouette, for checking the AI visual
  dwelling-outline.png      its whole outline, nothing in front of it, likewise
  visual.png, visual.json   the AI visual and its check (accepted attempts)
```

`python -m button_nz.sample` packs a design and the designs it revises into
one archive, as the submission's sample artifacts.

## The repository's documents

| Document | For |
|---|---|
| [README.md](../README.md) | What it is, how it works, the Meta models, how to run it |
| [product.md](product.md) | The problem, the product and where it goes next |
| [features.md](features.md) | Every feature, where it lives, and what it doesn't do |
| [user-journeys.md](user-journeys.md) | Who uses it, and each journey step by step |
| [information-architecture.md](information-architecture.md) | This page |
| [results/](results/README.md) | The experiments and the town screen, from live runs |
| [suppliers.md](suppliers.md) | Prefab suppliers, professionals, trades and the council, sourced |
| [deploy.md](deploy.md) | Serving it for judging |
| [submission.md](submission.md), [pitch.md](pitch.md) | The hackathon submission |
| [plan.md](plan.md), [architecture.md](architecture.md) | The original plan and the code's layout |
| [../data/README.md](../data/README.md) | The demo site's data, licences and open items |
