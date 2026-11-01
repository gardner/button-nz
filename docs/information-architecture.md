# Information architecture

How Button NZ's content is organised: the one page people use, the data
behind it, the API that serves it, and the files a design run leaves. For what
each part does, see [features.md](features.md); for who uses it and how, see
[user-journeys.md](user-journeys.md).

## The page

Button NZ is one page (`apps/web/app/page.tsx`), served at https://button.nz.
It has two columns: the site on the left and the design on the right. On a
narrow screen the site comes first.

```
Button NZ
Housing concepts for a real property, designed by an AI agent in Blender and
checked against the measured site.
├── The site (SiteSection)
│   ├── Site panel (SitePanel)
│   │   ├── Name, title and valuation number
│   │   ├── Site plan, north up: parcels, aerial photo, surveyed features, plan key
│   │   ├── Sources: each dataset's title, licence, attribution, and capture dates where recorded
│   │   └── Still to confirm: the site's open items
│   └── What is on the site (FeaturesPanel)
│       ├── Fixed-survey note: who decided it, when the server has fixed it
│       ├── One card per surveyed feature (#1 shed, #3 tree, …)
│       │   ├── What SAM 3.1 found, its area, height and the LiDAR's agreement
│       │   └── Decision: Existing building · Keep clear · Ignore
│       └── Every building on the site is listed (checkbox)
└── The design (DesignPanel)
    ├── Brief (BriefForm): the owner's words, and "Let the model request LiDAR views"
    ├── Design history: the original and each revision (once there is more than one)
    └── The design on show (DesignView)
        ├── Placing the <product>: walls L × W m (a placed prefab only)
        ├── Status line: queued, running, accepted, no attempt passed, or failed
        ├── Before and after (a revision only)
        ├── Attempt 1…n: verdict, each check's result in words (with its
        │   measurement), the LiDAR views asked for, the render, the AI
        │   illustration, View in 3D
        ├── 3D model (ModelViewer)
        ├── Which real prefabs fit? (ProductsPanel, an accepted design only)
        │   ├── Each fitting product: size, area, rooms, price, exclusions,
        │   │   West Coast delivery, and "Place it on the site"
        │   ├── Products not checked (dimensions not labelled)
        │   ├── What "fits" means
        │   └── Next steps: PIM, licensed people, ground, records to the council
        └── Change this design (RevisionForm, an accepted design only)
```

### Addresses

| Address | What it shows |
|---|---|
| `/` | The site, its survey, and a blank brief |
| `/?design=<id>` | That design after the designs it revises, oldest first. The address bar follows the design on show, so any step can be shared |
| `/?code=<code>` | Only when the server has an access code: sets the access cookie and drops the code from the address |

## The content

Each object, what it holds, and where it comes from.

| Object | Holds | Source | Kept in |
|---|---|---|---|
| **Site** | Name, title, parcels, extent, rasters and vectors with licences and capture dates, open items | LINZ and Buller District Council open data, pinned and verified | `data/demo-site/site.json`, `parcels.geojson` |
| **Survey** | Features SAM 3.1 found on the aerial photo, each a polygon (SAM's mask isn't kept) with its concept, score, area, height where the LiDAR has one, status and note | `python -m button_nz.perception.survey` | `DATA/survey.geojson` |
| **Decision** | Building, keep clear or ignore, per feature; whether every building is listed | The owner, in the app | `DATA/button.db` (decisions, surveys) |
| **Design** (job) | Brief, whether it may observe, status, timestamps, accepted attempt, parent and instruction (a revision), placed product | The owner's brief or change | `DATA/button.db` (jobs) |
| **Attempt** | Verdict, feedback, LiDAR views asked for, the model's script and its measured result | The design loop | `DATA/button.db` (attempts), `DATA/runs/<job>/attempt-<n>/` |
| **Check** | Name, pass, fail or unknown, a plain detail, measurements, the rule it comes from. The page shows the name, verdict and detail; the measurements and rule are in the trace | The evaluator (`button_nz.evaluation`) | Each attempt's `attempt.json` |
| **Product** | Supplier, model, outside footprint, area and its basis, rooms, price or null, exclusions, West Coast note, sources; whether it can be placed | Suppliers' own pages | `data/catalogue/products.json` |
| **Placed product** | The product a design places, as the catalogue gave it then | The owner's "Place it on the site" | `DATA/button.db` (jobs.product) |
| **Survey record** | The survey's id and the decisions a design was checked against (not the survey's features themselves: a replaced survey can't be recovered from it) | The worker, as each design runs | `DATA/runs/<job>/survey.json` |

### Vocabulary

The page and the docs use these words consistently:

| Word | Means |
|---|---|
| Section | One parcel of land. A title can hold several |
| Survey | What SAM 3.1 found on the site, before anyone decides what it is |
| Keep clear | An area no design may build on (a tree, a garden) |
| Brief | What the owner wants, in their own words |
| Attempt | One script Muse wrote, built and measured |
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
```

A public server adds two limits: a daily cap on design runs (429 past it), and
a survey fixed as the owner decided it (403 on changes). See
[deploy.md](deploy.md).

## A design run's files

Each design keeps its files under `DATA/runs/<job>/`:

```
survey.json                 the survey's id and the decisions it was checked against
design.json                 the run's summary
attempt-<n>/
  attempt.json              the agent's trace: observations, script, verdict, feedback
  observation-<k>.png       the LiDAR views the model asked for
  scene.json                the georeferenced site scene
  design.py                 the model's Blender script
  script/design.blend       the Blender file it saved
  measurements.json         what the trusted pass measured
  design.glb, design.png    the measured design, exported and rendered
  dwelling-mask.png         its silhouette, for checking the AI visual
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
