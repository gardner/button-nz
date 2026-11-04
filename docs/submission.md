# Submission checklist

Submissions close **Wednesday 4 November 2026, 9:00 PM ET**, which is
**Thursday 5 November, 3:00 PM NZDT**. Below are the seven artifacts plan §15
requires, where each one is, and what is still open. "Owner" means the
property owner or the team lead. Nothing that needs their word is assumed,
and nothing still to be produced is given a number.

| # | Artifact | Where | State |
|---|---|---|---|
| 1 | Working application | `apps/web` + `button_nz.api`, served from this machine ([deploy.md](deploy.md)) | **Done.** Open at https://button.nz (no access code; no daily cap on design runs), any address, with the owner's survey fixed. The smoke check (`check.sh`) passes |
| 2 | Demo video | `scripts/demo/` records and cuts it from one live run | **Cut** (2 min 13 s) from the final take on 5 Nov, with the owner's survey. The team lead uploads it; its link goes in [pitch.md](pitch.md) |
| 3 | Source repository | https://github.com/gardner/button-nz, GNU GPL (`LICENSE`) | **Done.** Public |
| 4 | Technical README | [README.md](../README.md): architecture, the Meta models and where, data and licences, the sandbox, limitations, reproduction | **Done** |
| 5 | Evaluation report | [docs/results](results/README.md) | **Done:** Experiments A and C, the model comparison, the batch run, the AI visual, the town screen, impact and the SAM 3D experiment |
| 6 | Sample project artifacts | `python -m button_nz.sample` (below) | **Done:** the final take's design and its revision, on the [release](https://github.com/gardner/button-nz/releases/tag/submission-2026-11-05) |
| 7 | Product story | [docs/product.md](product.md); the submission text is [pitch.md](pitch.md) | **Done** |

## Open items

| # | What | Owner | Unblocks |
|---|---|---|---|
| 1 | **The submission portal's requirements:** the fields, the video's length and format, and whether a live URL is required | Owner (needs the team's login) | the form |
| 2 | **Upload the video** and put its link in [pitch.md](pitch.md) | Owner | the form |
| 3 | **Submit** on the portal | Owner (needs the team's login) | |

### SAM 3D Objects with LiDAR (#125)

**Done.** The LiDAR fixes SAM 3D's placement and scale, not its shape: with
it, roofs are 0.9–1.5 m from the held-out LiDAR, against 7–11 cm for the
Roofer baseline from the same points, so SAM 3D stays out of the app. The
measured comparison is in the [write-up](experiments/sam3d-lidar/README.md)
and [docs/results](results/README.md).

## 1. Working application

The app runs on one machine: the API, the web app, and Blender on an NVIDIA
GPU. Every design is a live call to the Meta Model API and a sandboxed Blender
run. [deploy.md](deploy.md) serves it from that machine as systemd services,
behind a Cloudflare tunnel. It adds:

- an optional access code (button.nz runs without one, so judges' links carry none);
- an optional daily cap on design runs (off on button.nz);
- the owner's survey, fixed;
- links that open a finished design at once.

`META_API_KEY` stays on the server, read by the API's service only. Plan §15's
deployed demonstration is live at https://button.nz, through the team's
Cloudflare tunnel; `scripts/deploy/check.sh https://button.nz ""` checks it,
and passes. The owner decided the demo site's survey on 5 November (NZDT),
and the server holds it fixed. A ready site can also be seen in 3D
("See it in 3D", #149): its LINZ aerial photo on its own LiDAR heights.

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
- shows the real prefabs that fit, and asks to place the largest on the site
  (in the final take, no attempt passed: see below).

`cut.py --intro` can open the cut on the demo site's relief fly-over (#149):
its LINZ aerial photo draped on its own LiDAR, made by
`python -m button_nz.bench.relief`, and captioned as not the live run.

**The final take** (5 Nov, NZDT; 2 min 13 s cut) ran live with the owner's
survey. The design was accepted on attempt 2, and the revision on attempt 1,
at 2.33 m from the title boundary (2 m required). The cut ends on the six real
prefabs that fit. The take then tried to place the largest, the Russley
Portables Methven (15 × 4.2 m). None of its three attempts passed: the first
put something below the floor, the second's script raised an error, and on the
third the floor would sit 1.24 m above the lowest ground on this slope, where
at most 1 m is allowed. The recording stopped before the verdict
showed, so the cut leaves the placement out rather than show it unfinished.

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
- **SAM 3D Objects with LiDAR**: placement and scale, not shape.

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

**Done:** the final take's design and its revision are packaged, with the
owner's survey, on the [release](https://github.com/gardner/button-nz/releases/tag/submission-2026-11-05):

```bash
python -m button_nz.sample DATA 08ad57fbfe8b4834a6e54693b70256bb sample.zip --survey-decided-by "the owner"
```

The sample command also packs the survey with its decisions, every attempt's
verdict (`sample.json`) and a README naming the sources and their licences.
The owner gave permission on 31 October 2026 to publish imagery and renders of
the site.

## Notes

- **Prefab quotes (#11):** ten of the 17 catalogue products have no published
  price, which only a quote from the supplier can give. Not needed for the
  submission; the app says "not published".
- **Nothing is capped on button.nz.** The team lead removed the daily design
  cap (#179): `install.sh` passes `--daily-designs` only when
  `BUTTON_DAILY_DESIGNS` is set, and never `--daily-sites`. Each design run is
  billed Meta Model API calls and each new site SAM 3.1 calls. Capping either
  again would be a change to `deploy.env` (designs) or `install.sh` (sites)
  and a redeploy.
- **The demo site's survey so far:** the takes and Experiment C used the
  team's decisions (`data/demo-site/decisions.json`), which mark two features
  as buildings. The owner says nothing is built on the site, so the final take
  uses the owner's decisions, and the results say which decisions each run
  used.
