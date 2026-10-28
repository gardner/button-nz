# Button NZ

Unlock the housing hiding in your backyard. Button NZ turns a real property
into interactive, evidence-backed 3D housing concepts using Meta AI models,
LINZ geospatial data, and Blender. See [docs/plan.md](docs/plan.md).

## Setup

```bash
uv sync
cp .env.example .env   # then fill in LINZ_BASEMAP_API_KEY; never commit .env
uv run pre-commit install
```

Pull requests are reviewed in CI by `.github/workflows/claude-review.yml`
(`anthropics/claude-code-action` on Opus, authenticated with the
`CLAUDE_CODE_OAUTH_TOKEN` secret from `claude setup-token`; the code is sent to
Anthropic). Findings arrive as review threads, and every thread must be resolved
before merge: fix it, or reply with why not and resolve it; the next review
reads those replies. Fork and Dependabot PRs skip the review (forks get no
secrets, and the token must never reach a freshly bumped action); review those
by hand. Only maintainers' and reviewer bots' comments reach the reviewer, and
it reads and runs everything through Claude Code's Bash sandbox, with no network
and no tokens in reach.

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
