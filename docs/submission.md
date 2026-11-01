# Submission checklist

Submissions close **Wednesday 4 November 2026, 9:00 PM ET**, which is
**Thursday 5 November, 3:00 PM NZDT**. Below are the seven artifacts plan §15
requires, where each one is, and what is still open. "Owner" means the
property owner or the team lead. Nothing that needs their word is assumed,
and nothing still to be produced is given a number.

| # | Artifact | Where | State |
|---|---|---|---|
| 1 | Working application | `apps/web` + `button_nz.api`, served from this machine ([deploy.md](deploy.md)) | **Done.** Open at https://button.nz (no access code; at most 30 design runs a day), any address, checked end to end |
| 2 | Demo video | `scripts/demo/` records and cuts it from one live run | **Blocked** on the demo survey (open item 1); the recorder is ready |
| 3 | Source repository | https://github.com/gardner/button-nz, GNU GPL (`LICENSE`) | **Done.** Public |
| 4 | Technical README | [README.md](../README.md): architecture, the Meta models and where, data and licences, the sandbox, limitations, reproduction | **Done** |
| 5 | Evaluation report | [docs/results](results/README.md) | **Done:** Experiments A and C, the model comparison, the batch run, the AI visual, the town screen and impact. The SAM 3D experiment is **pending** (open item 4) |
| 6 | Sample project artifacts | `python -m button_nz.sample` (below) | **Blocked** on the final take; the packager is built and tested |
| 7 | Product story | [docs/product.md](product.md); the submission text is [pitch.md](pitch.md) | **Done** |

## Open items

| # | What | Owner | Unblocks |
|---|---|---|---|
| 1 | **Decide the demo survey** for 35 Victory Street on button.nz: one shed the LiDAR disputes is left to decide, then tick "every building is listed". Then set `BUTTON_SURVEY_DECIDED_BY` and `BUTTON_SURVEY_ID` (the `survey_id` from `/api/site/features`) together in `deploy.env`, and rerun `install.sh` (#91) | Owner | the final take (2), the sample (6) |
| 2 | **The submission portal's requirements:** the fields, the video's length and format, and whether a live URL is required | Owner (needs the team's login) | the video's cut, the form |
| 3 | **Record and cut the final take** (`scripts/demo/record.py`, `cut.py`), then **package the sample** from it, and fill in pitch.md's video link | Team, once 1 is done | 2, 6 |
| 4 | **SAM 3D results** (#125, #138): request access to `facebook/sam-3d-objects` on Hugging Face and log in; then `get_weights_and_run.sh` runs and scores both conditions | Owner (access); team (the run) | the SAM 3D slot below |
| 5 | **Submit** on the portal | Owner (needs the team's login) | |

### SAM 3D Objects with LiDAR (#125)

**Pending.** No SAM 3D output exists yet: its weights are gated on Hugging
Face and access hasn't been granted. The held-out truth, the scorer and the
Roofer baseline are in #138 ([write-up](experiments/sam3d-lidar/README.md)).
When it has run, its measured comparison goes here and in
[docs/results](results/README.md), from the scorer's own output.

## 1. Working application

The app runs on one machine: the API, the web app, and Blender on an NVIDIA
GPU. Every design is a live call to the Meta Model API and a sandboxed Blender
run. [deploy.md](deploy.md) serves it from that machine as systemd services,
behind a Cloudflare tunnel. It adds:

- an optional access code (button.nz runs without one, so judges' links carry none);
- a daily cap on design runs;
- the owner's survey, fixed;
- links that open a finished design at once.

`META_API_KEY` stays on the server, read by the API's service only. Plan §15's
deployed demonstration is live at https://button.nz, through the team's
Cloudflare tunnel; `scripts/deploy/check.sh https://button.nz ""` checks it.
Its survey is fixed once the owner has decided it (open item 1).

## 2. Demo video

`scripts/demo/record.py` drives the real app in a headless browser and
records it. `scripts/demo/cut.py` cuts that recording to about two minutes,
with captions. Long live waits are sped up, with the speed on screen, and the
closing card's numbers come from the reports. See
[scripts/demo/README.md](../scripts/demo/README.md).

The final take (`record.py`, updated for the map-first page in #97):

- shows the survey as the owner decided it (a survey that isn't fixed fails
  the take before any paid call);
- enters a brief, designs, and waits for the AI visual;
- views the design in 3D, revises it, and shows before and after;
- shows the real prefabs that fit, and places the largest on the site.

Earlier takes showed the team's survey decisions, captioned as such; the
owner says those are wrong for this site, so the submission's video is the
final take.

## 5. Evaluation report

[docs/results](results/README.md) holds each run's own report and log:

- **Experiment C** on the surveyed and the plain site;
- **the design-model comparison**;
- **Experiment A**: the full run after the reminder fix (#60), with the first
  run kept for the record;
- **many real sections**: placement before and after the frontages and room;
- **the AI visual**: how often it passes its silhouette check;
- **the town screen** and **impact** scenarios for Reefton;
- **SAM 3D Objects with LiDAR**: pending (open item 4).

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

**To do (open item 3):** package the final take's folders, the accepted
design and its revision, as the sample, with
`python -m button_nz.sample DATA JOB_ID sample.zip --survey-decided-by "the owner"`.
The sample command also packs the survey with its decisions, every attempt's verdict
(`sample.json`) and a README naming the sources and their licences. The owner gave permission on 31 October 2026 to
publish imagery and renders of the site. Package the sample from the final
take, which uses the owner's survey (open item 1), not from the takes
so far: those measure separation from the two sheds, which the owner says
aren't buildings.

## Notes

- **Prefab quotes (#11):** ten of the 17 catalogue products have no published
  price, which only a quote from the supplier can give. Not needed for the
  submission; the app says "not published".
- **Site builds aren't capped on button.nz.** `install.sh` passes
  `--daily-designs` to the API but not `--daily-sites`, and each new site is
  billed SAM 3.1 calls. Whether to cap them before judging is the owner's
  call; it would be a change to `install.sh` and a redeploy.
- **The demo site's survey so far:** the takes and Experiment C used the
  team's decisions (`data/demo-site/decisions.json`), which mark two features
  as buildings. The owner says nothing is built on the site, so the final take
  uses the owner's decisions, and the results say which decisions each run
  used.
