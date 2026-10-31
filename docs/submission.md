# Submission checklist

Submissions close **Wednesday 4 November 2026, 9:00 PM ET**, which is
**Thursday 5 November, 3:00 PM NZDT**. Below are the seven artifacts plan §15
requires, where each one is, and what is still open. "Owner" means the
property owner or the team lead. Nothing that needs their word is assumed.

| # | Artifact | Where | State |
|---|---|---|---|
| 1 | Working application | `apps/web` + `button_nz.api`, run locally (README, "Run it") | Runs end to end live; **not deployed: a required gap** (see below) |
| 2 | Demo video | `scripts/demo/` records and cuts it from one live run | Two takes recorded; final take after Experiment A's re-run |
| 3 | Source repository | this repository, GNU GPL (`LICENSE`) | Public |
| 4 | Technical README | [README.md](../README.md) | Done |
| 5 | Evaluation report | [docs/results](results/README.md) | Done: Experiments A and C, and the model comparison |
| 6 | Sample project artifacts | each design run's attempt folder (below) | Produced by every attempt whose script ran; to be packaged |
| 7 | Product story | [docs/product.md](product.md) | Done |

## 1. Working application

The app runs on one machine: the API, the web app, and Blender on an NVIDIA
GPU. Every design is a live call to the Meta Model API and a sandboxed Blender
run. A public deployment needs:

- a GPU host;
- `META_API_KEY` kept on the server;
- a choice of how judges may use it, since each design costs model calls.

Plan §15 requires a deployed demonstration, so this is an **open required
gap**, not something the video or the run instructions replace. Unless the
portal's requirements say otherwise, it needs the owner's decision on where
and how to deploy.

## 2. Demo video

`scripts/demo/record.py` drives the real app in a headless browser and
records it. `scripts/demo/cut.py` cuts that recording to about two minutes,
with captions. Long live waits are sped up, with the speed on screen, and the
closing card's numbers come from the reports. See
[scripts/demo/README.md](../scripts/demo/README.md).

The takes so far show:

- the SAM 3.1 survey, with the team entering answers in the owner's place
  (the team's decisions, pending the owner's confirmation, and captioned so);
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
- **Experiment A**: the full run after the reminder fix (#60), with the first
  run kept for the record.

## 6. Sample project artifacts

An attempt whose script ran and was measured keeps all of these, under
`DATA/runs/<job>/attempt-<n>/`. An attempt whose script failed keeps only
`design.py`, `attempt.json` (with the error) and any observations, so check
the chosen sample's folders before packaging them.

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
revision, as the sample. The owner gave permission on 31 October 2026 to
publish imagery and renders of the site, so nothing now holds this back.

## Open: needs the owner

1. **The submission portal's requirements**, which need the team's login:
   video length and format, the fields, and whether a deployed URL is
   required.
2. **The owner's own survey of the site.** The owner says nothing is built on
   it, so the two features `data/demo-site/decisions.json` marks as buildings
   (the team's decisions) are not. The takes so far show those decisions; the
   final take uses the owner's.
3. **Quotes for the prefabs (#11).** The suppliers, products and local
   professionals are researched and sourced in [suppliers.md](suppliers.md).
   An accepted design shows the catalogue products that fit and the next
   steps; ten of the 17 have no published price, which only a quote from
   the supplier can give.
4. **Deployment:** where to host it (see 1 above).
