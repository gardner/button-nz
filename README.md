# Button NZ

Unlock the housing hiding in your backyard. Button NZ turns a real property
into interactive, evidence-backed 3D housing concepts using Meta AI models,
LINZ geospatial data, and Blender. See [docs/plan.md](docs/plan.md).

## Setup

```bash
uv sync
cp .env.example .env   # then fill in LINZ_BASEMAP_API_KEY; never commit .env
uv run pre-commit install   # installs pre-commit and pre-push hooks
```

Pushing runs `scripts/pre-push-review.sh`: it sends the outgoing diff to Claude
Code (`claude -p`, read-only) and blocks the push on P0-P2 findings, writing
them to `ISSUES.md`. Fix them, delete `ISSUES.md`, commit, and push again. The
diff is sent to Anthropic, so `claude` must be installed and logged in, and `jq`
and GNU `timeout` must be on PATH. macOS lacks `timeout`: run
`brew install coreutils` and add its `gnubin` directory to PATH.

## Run

```bash
uv run button-nz
uv run pytest
```

## Layout

- `src/button_nz/` — Python package (geo, lidar, perception, agent,
  blender_worker, evaluation, catalogue, api).
- `apps/` — Next.js web app, generated with the pnpm CLI (see apps/README.md).
- `tests/` — pytest suite. Write the failing test first.
- `scripts/` — quality-gate scripts run by pre-commit.
- `data/` — property data notes and provenance (see data/README.md).
- `docs/` — hackathon plan and architecture notes.
