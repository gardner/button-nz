# Button NZ

Unlock the housing hiding in your backyard. Button NZ turns a real property
into evidence-backed 3D housing concepts: Meta's models read the site and
design a small dwelling for it in Blender, and an independent evaluator checks
each design against New Zealand's granny-flat rules before anyone sees it.

It's live at **https://button.nz**: open to anyone, with at most 30 design
runs a day. Search any New Zealand address, or tap a section on Reefton's town
map. A site is built live from national open data wherever LINZ has 1 m LiDAR,
a recent aerial photo and the title's parcels. The demo site, 35 Victory
Street, Reefton (Buller District), is pinned to the exact data it was verified
against.

- **For judges:** [docs/submission.md](docs/submission.md) is the submission
  checklist, and [docs/pitch.md](docs/pitch.md) the submission text.
- **The evidence:** [docs/results](docs/results/README.md) holds every
  experiment's report and log.
- **The product:** [docs/product.md](docs/product.md), and
  [docs/features.md](docs/features.md) for what's built and where.
- **The full plan:** [docs/plan.md](docs/plan.md).

## How it works

```
 LINZ open data (any address)        Meta Model API
 ────────────────────────────        ──────────────
 title's parcels, roads, outlines,   SAM 3.1 ─────────┐
 newest 1 m LiDAR DEM + DSM,                          │
 region's best recent aerial photo                    │
        │                                             ▼
        ├──► terrain scene (Blender) ──┐   site survey: trees, sheds, beds,
        │                              │   cross-checked against the LiDAR
        └──► LiDAR views on request ◄──┤              │
             (hillshade, contours,     │   owner confirms what is there
             slope, cross-sections)    │              │
                                       ▼              ▼
                    Muse Spark writes a Blender Python script ◄─────┐
                                       │                            │
                    sandboxed Blender builds, measures, renders     │
                                       │                            │
                    independent evaluator: Schedule 1A checks ──────┘
                                       │      (verdict + render back to Muse,
                                       ▼       up to three attempts)
                    accepted design: GLB + render in the web app,
                    revisable in plain words ("move it 3 m back")
                                       │
                    Muse Image illustrates it; SAM 3.1 checks the
                    building is still the design's; real prefabs that
                    fit its footprint, and who to call next
```

1. **Site data.** `button_nz.sites` builds a site from a LINZ address, or
   from a tapped section whose title has no address:
   - the parcel under the address and every parcel on the same title(s), from
     LINZ NZ Primary Parcels, with the LINZ building outlines around them;
   - which title edges face a road, named from LINZ NZ Addresses: Roads, and
     which is the address's own street (`sites/frontages.py`);
   - the newest 1 m LiDAR DEM and DSM that both cover the site, found in
     LINZ's national elevation catalogue (`sites/stac.py`);
   - the region's aerial photo at 0.3 m or finer since 2015, preferring
     12.5 cm or finer, then the newest.

   Where any of these is missing, the build says which and stops: nothing is
   filled in. A site of more than 12 parcels, or wider than 200 m, is refused
   as more than a section. Each site is built once and kept. The demo site's
   record (`data/demo-site/site.json`) instead pins the Buller District Council
   parcels and the exact raster tiles it was verified against. The DEM and DSM
   become a georeferenced terrain scene in Blender (NZTM2000 metres around a
   local origin), and their difference, the nDSM, shows what stands above the
   ground.
2. **Perception.** SAM 3.1 segments the aerial photograph one concept at a time
   ("tree", "shed", "garden bed", …). Each mask becomes an NZTM polygon and is
   checked against the nDSM: a shed should stand up, a driveway shouldn't.
   Each feature is a building, an area to keep clear, or neither. The app
   suggests a decision where the evidence is plain (`perception/confirm.py`):
   a feature mostly off the title, a parked car or open ground is ignored, a
   building the LiDAR agrees with is a building, and vegetation is kept clear.
   What the LiDAR disputes, and raised ground nothing labelled, gets no
   suggestion: the owner is asked. The owner's decision always wins, and only
   the owner can say every building is listed.
3. **Design.** Muse Spark gets the brief, the site in local coordinates, the
   buildings and keep-clear areas, which title edges face which road and which
   is the street, and a contract for the script (one `Dwelling` mesh, built on
   the terrain). It is also told where a plain rectangle fits
   (`agent/room.py`): the room inside the setbacks, 2 m from the listed
   buildings and off the keep-clear areas, and its two largest rectangles,
   square to the title. Before each attempt it may ask
   for LiDAR views of the site: hillshade, contours, slope or height maps,
   cross-sections between two points, or elevation statistics over an area.
   It then writes a complete Blender Python script as a tool call.
4. **Build and measure.** The script runs in headless Blender inside a
   sandbox (below). A second, trusted Blender pass reloads only the model's
   objects, checks the contract, measures every triangle actually rendered,
   and exports the GLB and a Cycles render.
5. **Evaluate.** `button_nz.evaluation` measures the geometry itself, never
   the model's claims: on the title, setbacks from the title boundary and
   internal section lines, separation from confirmed buildings, internal floor
   area, single storey, height, floor level above the ground, and keep-clear
   areas. Each check is pass, fail or unknown, with its measurement and the
   rule it comes from. A failed check can't be argued away in prose. The
   verdict and the render go back to Muse for the next attempt.
6. **Revise.** An accepted design can be changed in plain words. Muse starts
   from the accepted script, and the evaluator checks the result again.
7. **Illustrate.** Muse Image turns a close-up of the trusted render, three
   times the dwelling's size, into a photograph of the same scene. Image
   models move and invent things, so SAM 3.1 finds the house in the
   illustration, and it is shown only if it overlaps the design's
   silhouette from the same camera, cut to the same close-up (IoU at least
   0.6), labelled AI-illustrated.
8. **Match real prefabs.** `button_nz.catalogue` holds 17 New Zealand prefab
   products, each with sourced dimensions, and its price where the supplier
   publishes one (seven do; see [docs/suppliers.md](docs/suppliers.md)). Of the
   14 whose dimensions are labelled, those whose rectangle fits inside the
   accepted footprint are shown, with what their price leaves out. The other
   three are listed as unchecked, never as fitting. The next steps go with
   them: the licensed professionals the exemption needs, and the council's
   records.
9. **Place a real prefab.** Any product that fits can be placed on the site.
   Muse designs again, with the product's outside footprint as the walls, and
   the evaluator checks they are that footprint (`product_footprint`, to
   0.10 m) before every other check runs on it. The brief also gives the
   product's roof as its supplier builds it, and the render shows the
   product's colours (`appearance` in the catalogue, each with its basis:
   published palette or illustrative) over the CC0 texture closest to its
   cladding and roofing: weatherboard, timber, sheet panels, corrugated or
   5-rib metal (`blender_worker/textures`, from Poly Haven). The trusted pass
   still renders exactly the measured triangles, in finishes the host sets,
   never the model, with texture coordinates in metres so every finish is
   shown at true scale.

## Meta models

| Model | Where | What for |
|---|---|---|
| `muse-spark-1.3` | `button_nz.agent.model` | the design agent: tool calls to Blender and the LiDAR views, reading its own renders |
| `muse-spark-1.3` | `button_nz.bench.answering` | Experiment A: answering terrain questions from images |
| `sam-3.1` | `button_nz.perception.sam` | segmenting the aerial photograph into site features, and checking each AI visual's house against the design |
| `muse-image-1.0` | `button_nz.perception.visual` | illustrating an accepted design from its trusted render |
| `muse-wonder-1.0` | `button_nz.bench.design_ablation --model` | compared with Spark as the design agent ([results](docs/results/README.md)) |

All of them are called through the Meta Model API (`https://api.meta.ai/v1`)
with `META_API_KEY`.

**SAM 3D Objects** is an experiment, not part of the app: can it reconstruct a
real house from our aerial photography, and does giving it the measured LiDAR
instead of its own depth estimate make that accurate
([write-up](docs/experiments/sam3d-lidar/README.md), #125)? The inputs, the
held-out truth, the scorer and a conventional baseline are being prepared
(#138). **Its results are pending**: SAM 3D's weights are gated on Hugging
Face, and access hasn't been granted yet.

## Evaluation

Every result comes from a live run, and each report is written by its
benchmark from its own log; nothing is filled in by hand. The reports and
their logs are in [docs/results](docs/results/README.md), which states each
run's code commit and what the samples can and can't show.

- **Experiment A: does Muse understand LiDAR?** (`button_nz.bench.lidar_qa`)
  - Objective questions about the demo site's terrain: which way a slope
    faces, the height difference between two points, relief within a square,
    the steepest of several squares, and the tallest feature.
  - Answers are computed from the DEM and nDSM.
  - Five conditions: the aerial photograph alone; with contours; with nDSM
    and slope maps; with every map; and with the observation tools the model
    can call itself.
- **Experiment C: what does feedback buy?** (`button_nz.bench.design_ablation`)
  - Each design brief is run on the demo site under four conditions:
    - one shot;
    - execution errors only;
    - the evaluator's verdict and render;
    - the verdict plus the LiDAR tools.
  - Measured: acceptance, execution and repair rates, attempts, and time.
  - `--model` compares design models (Muse Wonder against Spark).
- **Many real sections** (`button_nz.bench.batch`): drives the live API as
  the app does, building Reefton sections from their addresses and designing
  on each. Run before and after Muse was told the title's frontages and room.
- **The AI visual** (`button_nz.bench.visual_check`): how often Muse Image's
  picture passes its SAM 3.1 silhouette check, on recorded designs.
- **Town screen** (`button_nz.bench.town_screen`) uses no model: it counts
  Reefton's properties with room for a real prefab under the exemption's
  siting rules. **Impact** (`button_nz.bench.impact`) turns that count into
  housing scenarios against the 2023 Census.

## Security

Model-written code is untrusted. Each script runs in Blender under bubblewrap
and systemd, with:

- no network, and private IPC, PID and `/dev`;
- a read-only system and a size-limited tmpfs home;
- a cleared environment, so no API key reaches the script;
- limits on memory, tasks and time;
- the GPU only for the trusted render pass.

The model's output comes back over a pipe, never through the host's disk. The
API serves only named artifacts, as regular files, never through a symlink.

## Data and licences

Every site records each dataset it was built from, with its licence,
attribution and capture dates where known; `GET /sites/{id}` (and `/site` for
the demo site) returns them, and the map credits them.

**Any address** is built from LINZ's national open data, all CC BY 4.0,
attributed to Toitū Te Whenua Land Information New Zealand (and, for LiDAR and
aerials, the providers each collection names):

| Data | Source |
|---|---|
| Addresses and roads | LINZ NZ Addresses; LINZ NZ Addresses: Roads |
| Parcels and titles | LINZ NZ Primary Parcels |
| Building outlines | LINZ NZ Building Outlines |
| 1 m LiDAR DEM and DSM | the newest LINZ elevation collection covering the site (`nz-elevation` on AWS) |
| Aerial photo | the region's best recent LINZ imagery collection (`nz-imagery` on AWS) |
| Basemap | LINZ Basemaps aerial tiles (needs `LINZ_BASEMAP_API_KEY`) |

**The demo site** is pinned to these, all CC BY 4.0 except Buller District
Council's parcels and zones, whose layers state no licence, so none is claimed
([data/README.md](data/README.md), "Parcel licence"):

| Data | Source | Captured |
|---|---|---|
| 1 m LiDAR DEM and DSM | West Coast LiDAR (2020–2024) | 2020-05 to 2024-07 |
| 7.5 cm aerial photo | Buller Urban Aerial Photos (2024–2025) | 2024-12 to 2025-09 |
| Parcels | Buller District Council property parcels | |
| Building outlines | LINZ NZ Building Outlines (none on these parcels) | 2015-12 to 2016-06 |

The owner gave permission on 31 October 2026 to publish imagery and renders of
the demo site.

**The town screen** uses Buller District Council's parcels and Residential
zones, LINZ's building outlines and the West Coast LiDAR; **the impact
scenarios** add Stats NZ's 2023 Census place summary for Reefton (CC BY 4.0).
Each report lists its sources.

**Prefabs:** the catalogue's dimensions and prices are from each supplier's
own pages, cited per product ([docs/suppliers.md](docs/suppliers.md)).
The render's cladding and roofing textures are CC0 1.0, from Poly Haven
([credits](src/button_nz/blender_worker/textures/README.md)).

Source code is under the GNU GPL (see `LICENSE`).

## Limitations

- **Where it works.** A site needs LINZ 1 m LiDAR, a recent aerial photo
  (0.3 m or finer, since 2015) and a parcel with a record of title. Where one
  is missing, the build says which and stops. A site of more than 12 parcels
  or wider than 200 m is refused. The demo site is the one verified
  end to end by hand; other sites are built and designed on live, as they
  come.
- **What the checks cover.** They cover the Schedule 1A granny-flat
  exemption's measurable conditions, not a building consent, the district
  plan, natural hazards or services. Whether the lines between sections on
  one title count as legal boundaries is unconfirmed, so a design close to one
  is "unknown", not "pass".
- **Imagery age.** The LiDAR and the aerial photo are often captured years
  apart (on the demo site, 2020–24 and 2024–25), and LINZ's building outlines
  can be older still, so the site may have changed. That is why the owner
  decides the survey.
- **Prefabs.** Fits use each product's stated dimensions; most suppliers
  don't publish eaves, so a fit isn't a setback verdict for that product. Ten
  of the 17 products publish no price.
- **The AI visual** passes its silhouette check on only some designs
  ([results](docs/results/README.md)); when it fails, no picture is shown.
- **One shared server.** No accounts: a design is open to anyone with its
  link, and design runs are capped per day.
- **Open item** for the demo site: the owner's own survey. The owner says
  nothing is built on it, so the two features the survey took for sheds are
  not buildings; the owner decides them on the live site before the final
  demo take ([docs/submission.md](docs/submission.md)).

## Run it

To serve it for others, open or behind an access code, see [docs/deploy.md](docs/deploy.md).

You need:

- Linux with an NVIDIA GPU, for Blender's Cycles;
- Python 3.14 with [uv](https://docs.astral.sh/uv/), and Node with pnpm;
- `bwrap` (bubblewrap) and a systemd user session (`systemd-run --user`), for
  the sandbox;
- a Meta Model API key (`META_API_KEY`) for anything that calls a model, and
  a LINZ Basemaps key (`LINZ_BASEMAP_API_KEY`) for the map's aerial tiles.

```bash
uv sync
cp .env.example .env          # set META_API_KEY and LINZ_BASEMAP_API_KEY; never commit .env
uv run pre-commit install
uv run pytest                 # the fast suite; -m blender and -m live are opt-in
```

**Blender:** use the official blender.org build (Ubuntu's package has no
OptiX). Unpack it under `~/.local/opt/`, and put a `blender` launcher on the
`PATH` (e.g. in `~/.local/bin/`). `uv run pytest -m blender` runs the Blender
tests.

**API:** this runs design jobs one at a time, keeping jobs, sites and their
files under `var/`. Survey the demo site first, so the owner has something to
decide. This writes `var/survey.geojson`:

```bash
uv run --env-file .env python -m button_nz.perception.survey var
uv run --env-file .env python -m button_nz.api.serve --port 8000
curl localhost:8000/site                     # the demo site and its sources
curl 'localhost:8000/addresses?q=35+victory+reefton'   # each address's id
curl -X POST localhost:8000/sites -H 'content-type: application/json' \
  -d '{"address_id": <an address id>}'      # the site's id; built once, in the background
curl localhost:8000/sites/<site_id>         # its build's status and step, then the site
curl -X POST localhost:8000/designs -H 'content-type: application/json' \
  -d '{"brief": "A small one-bedroom studio.", "site_id": "<site_id>"}'
curl localhost:8000/designs/<id>            # status, attempts and artifact URLs
curl -X POST localhost:8000/designs/<id>/revisions -H 'content-type: application/json' \
  -d '{"instruction": "Move it further from the street."}'
```

A design with no `site_id` is on the demo site. `serve` also takes
`--daily-designs N` and `--daily-sites N` to cap runs and site builds a day,
and `--survey-decided-by NAME --survey-id ID` (together) to fix the demo
site's survey as the owner decided it.

**Web app:** this proxies `/api` to the API (`BUTTON_API_URL`, by default
`http://127.0.0.1:8000`). Open http://localhost:3000.

```bash
cd apps/web && pnpm install && pnpm dev
```

**One design from the command line,** on the demo site, without the API:

```bash
uv run --env-file .env python -m button_nz.agent.demo runs/demo "A small studio."
```

**Benchmarks:** each writes `results.jsonl` as it goes, and `report.md` at the
end. The commands each run used are in [docs/results](docs/results/README.md).

```bash
uv run --env-file .env python -m button_nz.bench.lidar_qa out/lidar-qa
uv run --env-file .env python -m button_nz.bench.design_ablation out/design-ablation
uv run python -m button_nz.bench.town_screen out/town-screen
uv run python -m button_nz.bench.batch --api http://127.0.0.1:8000 --sections 20 --out out/batch
uv run --env-file .env python -m button_nz.bench.visual_check var/runs DESIGN_ID...
```

**Sample artifacts:** pack an accepted design and the designs it revises
(pass the latest revision), with the survey they were checked against:

```bash
uv run python -m button_nz.sample var JOB_ID sample.zip --survey-decided-by "the owner"
```

## Layout

- **`src/button_nz/`:**
  - `geo`: LINZ and Buller clients, NZTM, terrain, aerial tiles;
  - `sites`: building a site from any address or title, from LINZ's layers
    and STAC catalogues, its frontages, and the site store;
  - `lidar`: views and analysis;
  - `perception`: SAM, georeferenced features, the survey, the owner's
    decisions and their suggestions, and the AI visual;
  - `agent`: the Muse design loop, and the site, frontages and room it's told;
  - `blender_worker`: scene building, the sandbox, the trusted measuring
    pass, the CC0 textures;
  - `evaluation`: the checks;
  - `catalogue`: the prefab products and which fit;
  - `town`: the town screen and its map;
  - `bench`: the experiments;
  - `sample`: packing sample artifacts;
  - `api`: the HTTP service.
- **`apps/web/`:** the Next.js app: the town map and address search, the
  survey, live design runs, the 2D/3D map and model viewer, revisions and
  prefabs.
- **`scripts/`:** deployment (`deploy/`) and the demo recording (`demo/`).
- **`tests/`:** the pytest suite, written test-first.
- **`data/`:** the demo site record and its provenance, and the prefab
  catalogue.
- **`docs/`:** the plan, the product, the results and the submission.

## Development

Pre-commit enforces:

- a 500-line limit per file;
- Ruff lint with McCabe complexity ≤ 10;
- Ruff format;
- Pyright in strict mode;
- ShellCheck.

CI runs the same Python checks with the test suite, and ESLint, Prettier and
Vitest for the web app.

Pull requests are reviewed in CI by two AI reviewers, each through
`anthropics/claude-code-action`:

- **`.github/workflows/claude-review.yml`:** Claude Opus, authenticated with
  the `CLAUDE_CODE_OAUTH_TOKEN` secret. The code is sent to Anthropic. It's a
  required check.
- **`.github/workflows/zai-review.yml`:** Z.ai's GLM, through Z.ai's
  Anthropic-compatible endpoint, with the `ZAI_API_KEY` secret. The code is
  sent to Z.ai. It's not a required check, but its threads are handled the
  same way.

How the reviews work:

- **Threads:** findings arrive as review threads, and every thread must be
  resolved before merge. Either fix it, or reply with why not and resolve it.
  The next review reads those replies.
- **Fork and Dependabot PRs** skip the review (forks get no secrets, and the
  token must never reach a freshly bumped action), so review those by hand.
- **Isolation:** each reviewer runs in Claude Code's Bash sandbox, with no
  network and no tokens in reach. The keys reach the workflows only on
  same-repository PRs, which need push access.
- **Records:** each run's metrics are in its job summary. GLM's cost there is
  Claude Code's estimate at Anthropic prices. Each transcript is kept for 90
  days as an encrypted artifact. `scripts/review-traces.sh` downloads and
  summarises the latest of both.
