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

Pushing runs `scripts/pre-push-review.sh`: headless Claude Code (`claude -p`)
reviews the outgoing commits and writes any P0-P2 findings to `ISSUES.md`, which
blocks the push. Fix them, delete `ISSUES.md`, commit, and push again. To
decline a finding, explain why in `BACKGROUND.md` (local, gitignored), which is
added to the reviewer's prompt. The code is sent to Anthropic, so `claude` must
be installed and logged in.

Pull requests are reviewed again in CI by `.github/workflows/claude-review.yml`
(`anthropics/claude-code-action`, authenticated with the `CLAUDE_CODE_OAUTH_TOKEN`
secret from `claude setup-token`). Findings arrive as review threads, and every
thread must be resolved before merge: fix it, or reply with why not and resolve
it; the next review reads those replies. CI and local reviews share one
subscription quota.

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
