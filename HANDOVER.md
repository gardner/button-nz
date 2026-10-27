# HANDOVER — Button NZ

Read this first, then [AGENTS.md](AGENTS.md). AGENTS.md governs how work is
done here. This file records where the project stands.

## What this is

Button NZ: "Unlock the housing hiding in your backyard." A homeowner enters
a real property; Meta AI models examine aerial imagery and LiDAR, write
Blender Python to build a georeferenced 3D site, place real prefab homes,
get checked by an independent evaluator, visibly fix failures, and connect
the surviving concept to a real product and next steps.

Meta Global AI Developer Hackathon entry. Indie track. Primary theme Push
the Frontier. Deadline 5 November 2026, 3:00 PM NZDT. Full plan:
[docs/plan.md](docs/plan.md). Strategy source (ChatGPT transcript, context
only): [docs/hackathon.md](docs/hackathon.md). Architecture:
[docs/architecture.md](docs/architecture.md).

Greenfield. There is no existing Button NZ platform. The hackathon P0 must
work end to end by 31 October. SAM 3D, DINOv3, Glimmer fine-tuning, and
Modal are stretch goals only.

## Current state

Master is at `f7a38b2` with four merged PRs:

- #1 Next.js app scaffold, TypeScript line gate, next-dev-loop skill.
- #2 Codex Review Gate workflow (later redesigned to completion-only).
- #3 Python and web CI quality workflows plus Dependabot.
- #21 AGENTS.md workflow rules (subagent monitoring, pre-push review).

What exists: a typed placeholder Python package with endpoint config and
12 passing tests, a stock Next.js template app that builds, full quality
gates locally and in CI, and issue-driven scope. No product features yet.
Open issues (#4 to #15, #20) are the work queue. Open PRs #16 to #19 are
Dependabot bumps awaiting triage.

## Repo map

- `src/button_nz/` Python package: `geo`, `lidar`, `perception`, `agent`,
  `blender_worker`, `evaluation`, `catalogue`, `api`, plus `config.py`
  (public service endpoints; keys never live here).
- `apps/web/` Next.js 16.4.3, React 19.3.0, Tailwind 4, strict TypeScript.
  Stock template UI. Generate or change it with the pnpm CLI, not by hand.
- `tests/` pytest. `scripts/` gate scripts. `data/` property notes and
  provenance. `.github/` workflows and Dependabot. `.agents/skills/`
  project skills, including `next-dev-loop` for runtime verification.

## Non-negotiables

From AGENTS.md. Do not re-litigate these without the owner:

- NO FALLBACKS. Accurate results matter. Fix the failing system or
  process. If you need help, stop and ask.
- Never bypass hooks with `--no-verify`. Never add fail-open hooks,
  opt-out env vars, or silent substitute data paths.
- TDD red, green, refactor. Write the failing test first.
- Max 500 lines per file for first-party `.py`, `.ts`, `.tsx` source.
  Strong types, formatting, complexity caps on both stacks (see CI below).
- Descriptive commits. Branch per issue, PR when ready, merge commits.
  Keep the GitHub Project board up to date:
  https://github.com/users/gardner/projects/4
- Before picking up an issue: review it, review the code, research, then
  expand the issue with The Problem, proposed plan, and options considered.
- PR monitoring uses a subagent with the owner's exact model wording in
  AGENTS.md. Keep that text verbatim.
- Pre-push review (AGENTS.md section, hook tracked in #20): until the hook
  lands, run the headless Claude review loop manually on non-trivial
  changes. Findings go to `ISSUES.md`; fix relevant ones, delete
  `ISSUES.md`, push again. `ISSUES.md` is transient; never commit it.
- Review `git diff` before every `git add`. The owner edits files live in
  this worktree; do not sweep unseen edits into your commits.

## Review machinery

Codex reviews are subscription-based and trigger on push. Never comment
`@codex review` to invoke one. Push and monitor instead.

- `codex-review-gate` (required status check): passes once Codex completes
  a review of the exact PR head commit. It does not judge findings.
- Branch ruleset on the default branch (`master`): requires a PR, the
  gate check, and resolution of all review conversations. That native
  resolution rule is what enforces findings. Resolving updates merge
  eligibility instantly.
- Triage every finding yourself. Fix real ones with a new commit, reply
  with evidence, then resolve the thread. For owner-policy rejections
  (for example scoping the NO FALLBACKS ban), reply that it is intentional
  owner directive and resolve. Codex can be wrong: it claimed this repo's
  branch was `main` (it is `master`) and overstated a lockfile breakage.
  Verify against the repository before changing code.
- `python-quality` and `web-quality` workflows mirror local gates and run
  in seconds. They are green on every PR so far but are not yet required
  checks; adding them to the ruleset is a pending owner decision.
- Dependabot watches GitHub Actions and `apps/web` npm weekly. Python
  upgrades stay deliberate: `uv lock --upgrade`.
- Caveat: the gate parses `codex-review-state:v1` comment metadata. It is
  observable, not a documented stable OpenAI API (openai/codex#27691).

## Environment

Verified on this machine: Python 3.14 with uv 0.13.6 (project `.venv` via
`uv sync`), Node v24.22.1, pnpm 12.15.0 (via `corepack enable pnpm`),
gh 2.103.3 logged in as gardner, Blender 5.0.1, RTX 5090 32 GB, Claude
Code CLI 2.1.312. Pre-commit hooks are installed; they run file-length,
Ruff, Ruff format, and strict Pyright on commit.

Secrets: this repo is PUBLIC. `LINZ_BASEMAP_API_KEY` lives only in `.env`
(gitignored, mode 600). Never commit it, including inside tile URLs. The
key is a temporary 90-day key. Public endpoints (Buller parcels, LINZ
addresses and building outlines, basemap tile templates) live in
[.env.example](.env.example) and `src/button_nz/config.py`; the wrapper
appends the key at request time.

## Demo property

35 Victory Street, Reefton. Verified: LINZ address ID 3213224, NZTM2000
(1505941.6, 5336793.7), Title 354613, ValNum 1905027200. Three main
sections 700, 701, 702 (survey area 309 each, address in 701), plus
Section 1336 (area 30) on the same title. Basemap WMTS (both grids) and an
aerial tile over the property returned HTTP 200. Building outlines nearby
derive from West Coast 2015-2016 aerial photos; treat as dated evidence.
Details: [data/README.md](data/README.md).

Not yet verified (gates for issue #4): whether Section 1336 is in the site
extent, DEM/DSM coverage over the parcels, imagery licensing for
publication, and owner permission to publish imagery and renders.

## Run and verify

```bash
uv sync && cp .env.example .env   # fill in the LINZ key; never commit .env
uv run pytest -q                   # 12 tests
cd apps/web && pnpm install --frozen-lockfile && pnpm lint && pnpm build
pnpm start                         # production server on :3000
```

At handover, a detached production server was already listening on
port 3000 from an earlier `pnpm exec next start -p 3000` in `apps/web`
(log `/tmp/button-web.log`). Do not assume it survives; check the port.

## Next steps, in order

1. Triage Dependabot PRs #16 to #19 individually. React patch is low risk.
   Treat TypeScript 6, @types/node 26, and github-script 9 as majors
   needing their own verification, not batch merges.
2. Issue #4 first: verify the demo property dataset end to end.
3. P0 chain: #5 geo clients, #6 terrain and Blender foundation,
   #7 independent evaluator, #8 Muse-to-Blender fail-then-fix loop.
   Provisional on-camera failure is a 2 m setback breach (owner may change).
4. Issue #11 is blocked on the owner's prefab supplier list.
5. Check authenticated submission-portal requirements early (issue #15).
   Do not discover a video limit in the final week.
6. Issue #20 (pre-push Claude hook) when P0 is stable. It must fail
   closed: plan-mode read-only review, `ISSUES.md` protocol, no opt-outs.

## Open owner questions

Prefab supplier list (blocks #11). Default Meta agent model, Wonder or
Spark (still unanswered). Submission-portal video and link requirements.
Practitioner reviewer for evaluation (issue #14). Publishing permission
and Section 1336 extent (issue #4). Whether to require `python-quality`
and `web-quality` in the branch ruleset.

## Traps

- Do not re-add a `packageManager` pin to `apps/web/package.json`. With
  pnpm 12 it prepends a second YAML document to `pnpm-lock.yaml`, which
  single-document tooling misreads. Regenerate locks; never hand-edit them.
- Plan section 16 lists fallback mitigations that predate NO FALLBACKS.
  Reconcile them per issue at pickup; AGENTS.md governs.
- `docs/hackathon.md` is a ChatGPT transcript. Useful context, sometimes
  wrong (it assumed an existing platform). `docs/plan.md` governs scope.
- Keep generated artifacts honest: distinguish live runs, cached results,
  and accelerated renders in anything a judge sees.
