# Button NZ

Unlock the housing hiding in your backyard. Button NZ turns a real property
into evidence-backed 3D housing concepts: Meta's models read the site and
design a small dwelling for it in Blender, and an independent evaluator checks
each design against New Zealand's granny-flat rules before anyone sees it.

The demo site is 35 Victory Street, Reefton (Buller District), built from
public LiDAR, aerial photography and parcel data. See [docs/plan.md](docs/plan.md)
for the full plan.

## How it works

```
 LINZ / Buller open data             Meta Model API
 ───────────────────────             ──────────────
 parcels, 1 m LiDAR DEM + DSM,       SAM 3.1 ─────────┐
 7.5 cm aerial photo                                  │
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

1. **Site data.** The demo site record (`data/demo-site/site.json`) pins the
   parcels and the raster tiles it was verified against. The LiDAR DEM and DSM
   become a georeferenced terrain scene in Blender (NZTM2000 metres around a
   local origin), and their difference, the nDSM, shows what stands above the
   ground.
2. **Perception.** SAM 3.1 segments the aerial photograph one concept at a time
   ("tree", "shed", "garden bed", …). Each mask becomes an NZTM polygon and is
   checked against the nDSM: a shed should stand up, a driveway shouldn't.
   Disagreements, and raised ground nothing labelled, go to the owner. Nothing
   SAM finds constrains a design until the owner confirms it as an existing
   building, an area to keep clear, or neither.
3. **Design.** Muse Spark gets the brief, the site in local coordinates, the
   confirmed buildings and keep-clear areas, and a contract for the script
   (one `Dwelling` mesh, built on the terrain). Before each attempt it may ask
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
7. **Illustrate.** Muse Image turns the trusted render into a photograph of
   the same scene. Image models move and invent things, so SAM 3.1 finds the
   house in the illustration, and it is shown only if it overlaps the
   design's silhouette from the same camera (IoU at least 0.6), labelled
   AI-illustrated.
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

## Evaluation

Two experiments are run on the demo site from real model calls only. Their
reports are written from the logged results, and nothing is filled in by hand.
The reports and their logs are in [docs/results](docs/results/README.md).

- **Experiment A: does Muse understand LiDAR?** (`button_nz.bench.lidar_qa`)
  - Objective questions about the terrain: which way a slope faces, the height
    difference between two points, relief within a square, the steepest of
    several squares, and the tallest feature.
  - Answers are computed from the DEM and nDSM.
  - Five conditions: the aerial photograph alone; with contours; with nDSM
    and slope maps; with every map; and with the observation tools the model
    can call itself.
- **Experiment C: what does feedback buy?** (`button_nz.bench.design_ablation`)
  - Each design brief is run under four conditions:
    - one shot;
    - execution errors only;
    - the evaluator's verdict and render;
    - the verdict plus the LiDAR tools.
  - Measured: acceptance, execution and repair rates, attempts, and time.

The [town screen](docs/results/town-screen/report.md)
(`button_nz.bench.town_screen`) uses no model: it counts the Reefton sections
with room for a real prefab under the exemption's siting rules.

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

All site data is CC BY 4.0, attributed to Toitū Te Whenua Land Information
New Zealand, Aerial Surveys, West Coast Regional Council and (for the urban
aerial photos) Buller District Council, except Buller District Council's
parcels and zones, whose layers state no licence
([data/README.md](data/README.md), "Parcel licence").

| Data | Source | Captured |
|---|---|---|
| 1 m LiDAR DEM and DSM | West Coast LiDAR (2020–2024) | 2020-05 to 2024-07 |
| 7.5 cm aerial photo | Buller Urban Aerial Photos (2024–2025) | 2024-12 to 2025-09 |
| Parcels | Buller District Council property parcels | |
| Building outlines | LINZ NZ Building Outlines (none on these parcels) | 2015-12 to 2016-06 |

The API's `/site` lists every source with its licence and capture dates.
The render's cladding and roofing textures are CC0 1.0, from Poly Haven
([credits](src/button_nz/blender_worker/textures/README.md)).
Source code is under the GNU GPL (see `LICENSE`).

## Limitations

- **One site.** The pipeline takes any NZTM site with LiDAR coverage, but only
  the demo site has been verified end to end.
- **What the checks cover.** They cover the Schedule 1A granny-flat
  exemption's measurable conditions, not a building consent. Whether the lines
  between sections on one title count as legal boundaries is unconfirmed, so a
  design close to one is "unknown", not "pass".
- **Imagery age.** The LiDAR (2020–24) and the aerial photos (2024–25) were
  captured years apart, and the site may have changed since. That is why the
  owner confirms the survey.
- **Open item** in `site.json`: the owner's own survey of the site. The
  owner says nothing is built on it, so the two features the survey took for
  sheds are not buildings. The owner gave permission on 31 October 2026 to
  publish imagery and renders of the site.

## Run it

To serve it for others, open or behind an access code, see [docs/deploy.md](docs/deploy.md).

Python 3.14 with [uv](https://docs.astral.sh/uv/), Node with pnpm, and an
NVIDIA GPU for Blender's Cycles.

```bash
uv sync
cp .env.example .env          # set META_API_KEY; never commit .env
uv run pre-commit install
uv run pytest                 # the fast suite; -m blender and -m live are opt-in
```

**Blender:** use the official blender.org build (Ubuntu's package has no
OptiX). Unpack it under `~/.local/opt/`, and put a `blender` launcher in
`~/.local/bin/`. `uv run pytest -m blender` runs the Blender tests.

**API:** this serves the demo site and runs design jobs one at a time, keeping
jobs and their files under `var/`. Survey the site first, so the owner has
something to confirm. This writes `var/survey.geojson`:

```bash
uv run --env-file .env python -m button_nz.perception.survey var
uv run --env-file .env python -m button_nz.api.serve --port 8000
curl localhost:8000/site
curl -X POST localhost:8000/designs -H 'content-type: application/json' \
  -d '{"brief": "A small one-bedroom studio."}'
curl localhost:8000/designs/<id>  # status, attempts and artifact URLs
curl -X POST localhost:8000/designs/<id>/revisions -H 'content-type: application/json' \
  -d '{"instruction": "Move it further from the street."}'
```

**Web app:** this proxies `/api` to the API.

```bash
cd apps/web && pnpm install && pnpm dev
```

**One design from the command line:**

```bash
uv run --env-file .env python -m button_nz.agent.demo runs/demo "A small studio."
```

**Benchmarks:** each writes `results.jsonl` as it goes, and `report.md` at the
end.

```bash
uv run --env-file .env python -m button_nz.bench.lidar_qa out/lidar-qa
uv run --env-file .env python -m button_nz.bench.design_ablation out/design-ablation
```

## Layout

- **`src/button_nz/`:**
  - `geo`: LINZ and Buller clients, NZTM, terrain, aerial tiles;
  - `lidar`: views and analysis;
  - `perception`: SAM, georeferenced features, the survey and the owner's
    decisions;
  - `agent`: the Muse design loop;
  - `blender_worker`: scene building and the sandbox;
  - `evaluation`: the checks;
  - `bench`: the experiments;
  - `api`: the HTTP service.
- **`apps/web/`:** the Next.js app: site plan, survey confirmation, live
  design runs, the 3D viewer.
- **`tests/`:** the pytest suite, written test-first.
- **`data/`:** the demo site record and its provenance.
- **`docs/`:** the plan and architecture notes.

## Development

Pre-commit enforces:

- a 500-line limit per file;
- Ruff lint with McCabe complexity ≤ 10;
- Ruff format;
- Pyright in strict mode;
- ShellCheck.

CI runs the same Python checks with the test suite, and ESLint, Prettier and
Vitest for the web app.

Pull requests are reviewed in CI by `.github/workflows/claude-review.yml`
(`anthropics/claude-code-action` on Opus, authenticated with the
`CLAUDE_CODE_OAUTH_TOKEN` secret; the code is sent to Anthropic):

- **Threads:** findings arrive as review threads, and every thread must be
  resolved before merge. Either fix it, or reply with why not and resolve it.
  The next review reads those replies.
- **Fork and Dependabot PRs** skip the review (forks get no secrets, and the
  token must never reach a freshly bumped action), so review those by hand.
- **Isolation:** the reviewer runs in Claude Code's Bash sandbox, with no
  network and no tokens in reach.
- **Records:** each run's metrics are in its job summary. Its transcript is
  kept for 90 days as an encrypted artifact. `scripts/review-traces.sh`
  downloads and summarises the latest ones.
