# Submission checklist

Submissions close **Wednesday 4 November 2026, 9:00 PM ET**, which is
**Thursday 5 November, 3:00 PM NZDT**. Below are the seven artifacts plan §15
requires, where each one is, and what is still open. "Owner" means the
property owner or the team lead. Nothing that needs their word is assumed.

| # | Artifact | Where | State |
|---|---|---|---|
| 1 | Working application | `apps/web` + `button_nz.api`, run locally (README, "Run it") | Runs end to end live; **not deployed** (see below) |
| 2 | Demo video | `scripts/demo/` records and cuts it from one live run | Two takes recorded; final take after Experiment A's re-run |
| 3 | Source repository | this repository, GNU GPL (`LICENSE`) | Public |
| 4 | Technical README | [README.md](../README.md) | Done |
| 5 | Evaluation report | [docs/results](results/README.md) | Experiment C done; Experiment A re-running |
| 6 | Sample project artifacts | each design run's attempt folder (below) | Produced by every run; to be packaged |
| 7 | Product story | [docs/product.md](product.md) | Done |

## 1. Working application

The app runs on one machine: the API, the web app, and Blender on an NVIDIA
GPU. Every design is a live call to the Meta Model API and a sandboxed Blender
run. A public deployment needs:

- a GPU host;
- `META_API_KEY` kept on the server;
- a choice of how judges may use it, since each design costs model calls.

That is the owner's decision. Until then, the video and the README's run
instructions stand in for it.

## 2. Demo video

`scripts/demo/record.py` drives the real app in a headless browser and
records it. `scripts/demo/cut.py` cuts that recording to about two minutes,
with captions. Long live waits are sped up, with the speed on screen, and the
closing card's numbers come from the reports. See
[scripts/demo/README.md](../scripts/demo/README.md).

The takes so far show:

- the owner confirming the SAM 3.1 survey;
- Muse designing;
- a failed attempt and its repair;
- every check with its measurement;
- the labelled AI visual;
- the 3D model;
- a plain-words revision, with before and after.

## 5. Evaluation report

[docs/results](results/README.md) holds each run's own report and log:

- **Experiment C** on the surveyed and the plain site;
- **the design-model comparison**;
- **Experiment A**: its first full run, and its re-run (in progress) after
  the reminder fix (#60).

## 6. Sample project artifacts

Every design attempt keeps, under `DATA/runs/<job>/attempt-<n>/`:

| File | What it is |
|---|---|
| `scene.json` | the georeferenced site scene: terrain, nDSM, parcels, local frame |
| `script/design.blend` | the Blender file the model's script saved |
| `design.py` | the model's Blender Python script |
| `design.glb`, `design.png` | the measured design, exported and rendered |
| `measurements.json` | what the trusted pass measured |
| `attempt.json` | the agent's trace: observations, script, verdict and feedback |
| `observation-<k>.png` | the LiDAR views the model asked for |
| `visual.png`, `visual.json` | the AI visual and its silhouette check (accepted designs only) |

**To do:** package one demo run's folders, the accepted design and its
revision, as the sample. This waits on the open item below.

## Open: needs the owner

1. **Permission to publish imagery and renders of the site** (an open item in
   `data/demo-site/site.json`). The video, the sample artifacts and the
   survey all show it.
2. **The submission portal's requirements**, which need the team's login:
   video length and format, the fields, and whether a deployed URL is
   required.
3. **Confirmation of what stands on the site.** The survey decisions in
   `data/demo-site/decisions.json` are the team's, labelled as pending this.
4. **The supplier list for the prefab catalogue (#11).** Without it, the
   product, cost and next-steps view is not built.
5. **Deployment:** whether to deploy, and where (see 1 above).
