# Architecture

Button NZ is a greenfield monorepo. There is no existing platform to reuse.
See [plan.md](plan.md) for the full hackathon plan.

## Flow

A site is built from a LINZ address, or a tapped section's title: its parcels,
road frontages and building outlines from LINZ's national layers, and the
newest 1 m LiDAR and the region's best recent aerial from LINZ's STAC
catalogues. The demo site is pinned to the exact data it was verified against
instead. SAM 3.1 surveys the aerial, each feature checked against the LiDAR,
and the owner decides what each one is. The Muse agent asks for LiDAR views
and writes Blender Python to build a dwelling on the georeferenced terrain; a
sandboxed Blender runs it, a trusted pass measures it, and an independent
evaluator checks the geometry against the exemption's measurable rules. The
verdict and render go back to Muse until a design is accepted. The web app
shows it in 2D and 3D on the map, with its checks, revisions, a checked AI
visual, and the real prefabs that fit. The [README](../README.md) has the
diagram and each step.

Everything runs on one machine with an NVIDIA GPU, served as systemd services
behind a Cloudflare tunnel ([deploy.md](deploy.md)).

## Packages

- `button_nz.geo` — ArcGIS clients, coordinate transforms, terrain data, aerial tiles.
- `button_nz.sites` — building a site from any address or title, its frontages, the site store.
- `button_nz.lidar` — hillshade, contours, slope, cross-section tools.
- `button_nz.perception` — SAM masks georeferenced and checked against the LiDAR,
  the owner's decisions and their suggestions, the AI visual.
- `button_nz.agent` — Muse tool loop, the site, frontages and room it's told, and revisions.
- `button_nz.blender_worker` — sandboxed headless Blender execution and the trusted measuring pass.
- `button_nz.evaluation` — deterministic checks. The model cannot override
  a failed check with prose.
- `button_nz.catalogue` — real prefab products with sourced dimensions, and which fit.
- `button_nz.town` — the town screen and its map.
- `button_nz.bench` — the experiments; `button_nz.sample` — packing sample artifacts.
- `button_nz.api` — Python HTTP service for the web app.
- `apps/web` — Next.js frontend, generated with `pnpm create next-app`.

## Quality gates

Pre-commit runs a 500-line-per-file limit for Python and TypeScript
source, Ruff lint with McCabe complexity,
Ruff format, and Pyright in strict mode. Configuration lives in
`pyproject.toml` and `.pre-commit-config.yaml`. Tests use pytest with a
red-green-refactor workflow.

## Coordinates

Site work uses NZTM2000 (EPSG:2193) metres. Blender scenes use a local
metre-based origin derived from NZTM coordinates.
