# Architecture

Button NZ is a greenfield monorepo. There is no existing platform to reuse.
See [plan.md](plan.md) for the full hackathon plan.

## Flow

Property discovery (LINZ addresses, Buller parcels, basemap aerial tiles)
feeds site perception (SAM) and LiDAR visualisations. The Muse agent writes
Blender Python to build and revise a georeferenced 3D scene. An independent
evaluator checks geometry and supported planning constraints. The web app
presents interactive GLB scenes, renders, and a matched prefab product.

Blender runs on the local GPU only. Modal is a stretch goal.

## Packages

- `button_nz.geo` — ArcGIS clients, coordinate transforms, terrain data.
- `button_nz.lidar` — hillshade, contours, slope, cross-section tools.
- `button_nz.perception` — SAM masks georeferenced against GIS evidence.
- `button_nz.agent` — Muse tool loop and design revisions.
- `button_nz.blender_worker` — sandboxed headless Blender execution.
- `button_nz.evaluation` — deterministic checks. The model cannot override
  a failed check with prose.
- `button_nz.catalogue` — real prefab products with sourced dimensions.
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
