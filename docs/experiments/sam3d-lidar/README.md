# Experiment: SAM 3D Objects conditioned on LiDAR

**Status:** done. SAM 3D ran on both buildings, with and without the LiDAR
pointmap, over six seeds each. It was scored against held-out LiDAR points
alongside Roofer, a conventional method given the same training points.
**Decision: LiDAR-conditioned SAM 3D models don't go into the app's 3D
view** ([Results](#results)).

- **Done:**
  - **Held-out truth:** LINZ's raw LAS/LAZ points for the scene, split into
    held-out blocks and training points, with a DSM and DEM made from the
    training points alone ([below](#held-out-truth)).
  - **Inputs remade from the training points:** both buildings' oblique
    photos, pointmaps and masks ([inputs/](inputs/)).
  - **The scorer**, shape and layout, self-tested on known distortions
    ([below](#the-scorer)).
  - **Conditions 1–3, SAM 3D**, run with the official weights and scored
    ([Results](#results)). Condition 3 is the scorer's alignment, fitted to
    the training points.
  - **Condition 4, Roofer**, run and scored: its roofs sit 7–11 cm (median)
    from the held-out points by the scorer's measure, 3–5 cm read straight
    above each point ([below](#condition-4-roofer)).
- **Not measured:** roof-plane topology. Roofer reports its own planes;
  SAM 3D's meshes are dense marching-cubes surfaces with no planes to count.

## The question

Can Meta's SAM 3D Objects reconstruct a real house from aerial photography,
and does giving it measured LiDAR, instead of its own estimate of depth, make
that reconstruction accurate?

SAM 3D Objects turns a masked object in a photo into a 3D model: shape,
texture and pose. Its geometry model can take an optional **scene pointmap**:
a 3D point for every pixel. The paper says this can come "from hardware
sensors (e.g., LiDAR on an iPhone)" ([SAM 3D, arXiv 2511.16624](https://arxiv.org/abs/2511.16624)),
but its results use depth estimated from the image itself, apart from its
layout evaluation on Aria Digital Twin, which uses that dataset's provided
sensor pointmaps.

As far as we know, nobody has fed it survey LiDAR.

- SAM 3D has been run on remote-sensing images from the image alone
  ([arXiv 2512.22452](https://arxiv.org/abs/2512.22452)), judged by image
  similarity (FID and CLIP-based CMMD), with no measured ground truth.
- We have both:
  - LINZ's 1 m LiDAR ground and surface models (DEM and DSM) for any address
    they cover;
  - LINZ building outlines to measure against.

## Method

An aerial photo looks straight down, and SAM 3D is built for ordinary
photographs. So we make an ordinary-looking photo from our data:

1. **A virtual oblique photo.** In Blender, drape the aerial photo on the
   LiDAR surface (DSM) and render it from a perspective camera at about 45°,
   looking at one building.
2. **An exact pointmap for that photo.** Cast a ray through the same camera
   for every pixel and record where it meets the LiDAR surface. That gives
   one metric 3D point per pixel, in the camera's coordinates.
3. **The building's mask:** the pixels whose surface point falls inside its
   LINZ outline (plus 1 m) and stands more than 1 m above ground.
4. **Four conditions, each on the same photo and mask:**

   | Condition | What it tests |
   |---|---|
   | SAM 3D, its own MoGe depth | the baseline |
   | SAM 3D, the LiDAR pointmap | the main question |
   | SAM 3D, the LiDAR pointmap, then fitted to the training points | whether explicit fitting adds anything |
   | [Roofer](https://github.com/3DBAG/roofer), from the training points and the outline | a conventional, non-generative baseline |

5. **Measure two things apart.**
   - **Shape:** after the best scale and rigid alignment, is the roof right?
     - roof-surface RMSE;
     - roof-plane topology;
     - whether the model is a valid closed solid.
   - **Metric layout:** with no alignment, is it the right size and in the
     right place?
     - scale;
     - position;
     - roof height above ground;
     - footprint.

   Monocular depth has no scale at all, so a wrong scale isn't a bad shape;
   reporting the two apart keeps one from hiding the other.

6. **Measure against truth the model wasn't given.**
   - LINZ's 1 m DSM is made from all of its LAS/LAZ points. A model given
     inputs made from the DSM, and scored against the DSM or those points,
     is only tested on how faithfully it follows its input: **source-data
     fidelity**, reported as such, never as held-out truth.
   - For held-out truth, LINZ's LAS/LAZ points are split once: a held-out
     share (whole spatial blocks, so neighbouring points can't stand in for
     them), and the rest, the **training points**.
   - **Nothing a model is given may carry the held-out points.** From the
     training points alone we build our own surface, and every input comes
     from it:
     - the photo (step 1) is draped on it and rendered;
     - the pointmap (step 2) is cast onto it, so photo and pointmap agree
       pixel for pixel;
     - the mask's height test (step 3) uses it;
     - the fitting step (condition 3) fits to the training points only;
     - Roofer (condition 4) gets the training points themselves, not a
       raster, since it finds roof planes in a point cloud.
   - Each model is scored against the held-out points, which nothing it was
     given was made from.
   - Footprint IoU against the LINZ outline mostly tests adherence to the
     mask, which is drawn from that outline. It's reported as such, not as
     footprint discovery.
7. **Report the inputs as what they are:** the oblique photo is synthetic
   (an orthophoto draped on a 1 m surface), with no real walls. Results
   apply to synthetic oblique inputs, not to real oblique photography.

### How the pointmap goes in (verified in the code and the run)

- **Call path:** `Inference.__call__(image, mask, seed, pointmap=...)` in
  `notebook/inference.py`, then `InferencePipelinePointMap.run(pointmap=...)`,
  then `compute_pointmap()` in
  `sam3d_objects/pipeline/inference_pipeline_pointmap.py`. With no pointmap
  given, it runs MoGe instead.
- **Format:** an H×W×3 float tensor in PyTorch3D camera coordinates (x left,
  y up, z forward: OpenCV's with x and y negated). Missing pixels may be NaN.
- **Scale:** the pipeline normalises scale and restores it on the output, so
  metric LiDAR gives a model at roughly metric scale. In the run it came out
  about 18% (house) and 45% (behind trees) too big, against 17–22× too small
  with MoGe.

## What's known already

From research the owner gathered on [#125](https://github.com/gardner/button-nz/issues/125#issuecomment-6558069113).
Only the SAM 3D papers have been checked against their sources here; the
rest are as reported, not yet checked.

- **Meta's own ablation:** SAM 3D's appendix ("Pointmap Minimally Affects
  Shape") found people preferred the version with and the version without a
  pointmap equally often (48% each, on LVIS).
  - That's perceived shape, on everyday objects, not buildings in metres.
  - So the LiDAR's likely gain is metric layout (scale, position, height),
    not shape. Hence step 5's split.
- **SAM 3D on remote-sensing images** ([arXiv 2512.22452](https://arxiv.org/abs/2512.22452)):
  image-similarity metrics only, no metric comparison against LiDAR.
- **Fusing aerial imagery with LiDAR helps purpose-built models,** as
  reported for LoD2-Former (roof wireframes) and P³ (building polygons).
  - [P³](https://github.com/raphaelsulzer/PixelsPointsPolygons) includes LINZ
    data from Twyford, Waipukurau and Gisborne: aerial RGB, LiDAR and
    building polygons.
- **Visual quality isn't validity:** one 2026 study reports that only 0.6%
  of a generative model's building meshes were valid solids. Hence the
  validity measure.
- **External references, if time allows:** the ISPRS building
  reconstruction benchmark (Vaihingen, Toronto), with independent reference
  roofs; and Building3D (roof meshes and wireframes).
- **No published study** does exactly this experiment: SAM 3D with measured
  airborne LiDAR against SAM 3D with estimated depth, on real buildings,
  with metric evaluation.

## Held-out truth

- **Points:** LINZ's West Coast 2020–2022 LiDAR, tile
  `CL2_BS21_2020_1000_4629.laz` from OpenTopography's `NZ20_Westport`
  collection ([doi:10.5069/G9Z31WV0](https://doi.org/10.5069/G9Z31WV0),
  CC BY 4.0). NZTM2000, NZVD2016 heights, classified by LINZ (6 = building),
  about 6.6 points/m² over the house.
- **The split** ([`scripts/split.py`](scripts/split.py)): the scene's
  84 × 85 m box holds 53,095 points (noise dropped). 20% of its 2 m × 2 m
  blocks are held out (369 of 1,806, fixed seed), so a held-out point's
  neighbours are held out with it: **42,337 training points and 10,758
  held out**. The truth for each roof is the held-out building points inside
  its outline: 130 for the house, 165 for the building behind the trees.
- **Surfaces from the training points alone:** a 1 m DSM (highest point per
  cell) and DEM (lowest ground point), held-out blocks interpolated from the
  training cells around them. Against LINZ's own rasters
  ([`check_surfaces.py`](scripts/check_surfaces.py), output in
  [outputs/surfaces-vs-linz.json](outputs/surfaces-vs-linz.json)), the DEM
  differs by 2 cm (median) and the DSM by 5 cm (median; 1.2 m at the 90th
  percentile, at trees and edges, where LINZ's DSM carries the held-out
  points).
- **Every input is made from these:** the photos, pointmaps and masks
  ([`prep.py`](scripts/prep.py) with the training surfaces, then
  [`render_oblique.py`](scripts/render_oblique.py) and
  [`mask.py`](scripts/mask.py)); Roofer gets the training points themselves
  ([`roofer_inputs.py`](scripts/roofer_inputs.py)). The pointmap reprojects
  to its own pixel within 0.0007 px.

## The scorer

[`scripts/score.py`](scripts/score.py) reduces every model to points on its
surface, in the site's local frame. A mesh is sampled at 25 points per m²:
Roofer's model, and SAM 3D's own mesh, which SAM 3D decodes from the same
latent as its Gaussians and [`run_sam3d.py`](scripts/run_sam3d.py) poses
exactly as it poses them (`mesh.npz`). That mesh is SAM 3D's score, scored the
same way as Roofer's. Gaussian centres alone would drop each splat's size,
so a large splat could leave a gap in coverage or footprint. SAM 3D's active
Gaussian centres (opacity above 0.9, the cut SAM 3D's own code uses, so faint
floaters don't count) are scored too, as a secondary record. Then it
measures:

- **Layout, with no alignment:** the roof's vertical error at each held-out
  roof point (RMSE, median, and coverage: the share with model above them);
  roof height above ground (98th percentile) against the held-out points';
  footprint IoU against the LINZ outline (adherence to the mask, which came
  from the outline); and scale (the footprint's principal lengths over the
  outline's).
- **Shape, after the best similarity alignment** (scale, rotation,
  translation) of the model's top surface to the training-points DSM inside
  the outline: the same roof errors again. This alignment **is condition 3**:
  fitted to training points only, scored on held-out ones.
- **Validity** (meshes only): watertight, every edge on two faces.

A roof error with no held-out point under the model (coverage 0) is written
as `null`, not NaN, so every score file is strict JSON.

**Self-test** ([`scripts/selftest.py`](scripts/selftest.py), which fails if
any of this stops holding): Roofer's model of the house, as points and as a
mesh, distorted on purpose. Layout catches each distortion; shape is the same
after alignment, whatever the distortion and at any scale, so it measures
shape alone. A mesh is sampled as if it were the outline's size, and again at
true size after the alignment, so a mesh 20× too small has as many points as
a true-size one:

| Distortion | Roof median, no alignment | Footprint IoU | Fitted scale | Roof median, after alignment |
|---|---|---|---|---|
| None | 0.07 m | 0.90 | 0.96 | 0.15 m |
| Moved 3 m east, 1 m up | 0.87 m | 0.54 | 0.96 | 0.15 m |
| Turned 10°, 1.2× | 0.49 m | 0.64 | 0.78 | 0.15 m |
| 20× too big | 37.4 m | 0.002 | 0.048 | 0.15 m |
| 20× too small (as MoGe's raw depth is) | no model over any point | 0.01 | 18.8 | 0.15 m |
| As a mesh, 20× too big | 42.8 m | 0.002 | 0.048 | 0.15 m |
| As a mesh, 20× too small | no model over any point | 0.01 | 18.8 | 0.15 m |
| A copy of the house 60 m east, beside it | 0.07 m | 0.45 | (two houses) | (two houses) |

The footprint grid spans the outline and the whole model, so a model reaching
far beyond the outline is counted in full.

**The alignment has a floor, and it differs by building:** Roofer's own
model, which no alignment should improve, scores 0.15 m after it on the house
and 0.21 m on the building behind trees, against 0.07 and 0.11 m without it
([outputs/scores/](outputs/scores/)). The fit lifts the model: after it,
Roofer's roofs sit a median 0.15 m and 0.21 m above the held-out points
(`shape_roof_bias_m`), against 0.07 and 0.11 m before (`roof_bias_m`). The
likely cause is the target: the highest training point in each 1 m cell, set
at the cell's centre, sits above the roof there when the roof slopes. The fit
shrinks the house to scale 0.96 but not the other building (1.01), so the
shrinkage isn't the cause. Compare each building's shape numbers with its own
floor and with each other, not with the layout numbers.

**The roof measure leans upward too:** on a sloping roof, the highest model
point within 0.5 m of a held-out point is upslope of it. Read straight above
each held-out point instead (possible for meshes only, `roof_exact_*`),
Roofer's roofs are a median 3 cm (house) and 5 cm (behind trees) from the
held-out points, with no lean (−0.004 and −0.03 m). Every model gets the same
measure, so comparisons between them stand, but part of each roof error is
the measure's. Footprint and scale carry about one 0.5 m cell of
resolution (a perfect footprint scores about 1.05 in scale).

## Condition 4: Roofer

[Roofer](https://github.com/3DBAG/roofer) 1.0.0 (LoD 2.2), from the
training points and the LINZ outlines
([outputs/roofer/](outputs/roofer/), scores in
[outputs/scores/](outputs/scores/)):

| | House (179 m²) | Building behind trees (155 m²) |
|---|---|---|
| Roof error, median / RMSE (no alignment) | 0.07 / 0.19 m | 0.11 / 0.13 m |
| Held-out roof points with model above them | 100% | 94% |
| Roof height, model less held-out | +0.09 m | −0.09 m |
| Footprint IoU with the outline | 0.90 | 0.84 |
| Roof error read straight above each held-out point, median | 0.03 m | 0.05 m |
| Roof error after alignment (the alignment's floor), median / RMSE | 0.15 / 0.25 m | 0.21 / 0.22 m |
| Valid closed solid | yes (24 triangles) | yes (36 triangles) |

A conventional method, given the same training points, gets roofs within
about 10 cm by the scorer's measure (3–5 cm read straight above each point).
That's the bar for SAM 3D with the LiDAR pointmap.

Roofer counted 42% of the house's roof and 51% of the other building's as
no-data, and flagged both point clouds as insufficient coverage
(`rf_nodata_frac`, `rf_pc_select`). That is more than the 20% held out:
Roofer counts empty 0.5 m cells (its default), four to a square metre, and
with about 5.5 training points per m² (`rf_pt_density`) many cells are empty
outside the held-out blocks too.

## The depth input: MoGe against the LiDAR pointmap

SAM 3D without LiDAR uses MoGe (`Ruicheng/moge-vitl`) for depth. On the
photos made from the training points
([`scripts/moge_check.py`](scripts/moge_check.py),
[inputs/](inputs/)):

| | House (179 m², clear view) | Building behind trees (155 m²) |
|---|---|---|
| MoGe's raw scale vs metric | 19.9× too small | 19.9× too small |
| Focal length, true vs MoGe | 996 vs 1,371 px (38% off) | 996 vs 1,254 px (26% off) |
| Depth error on the building, after scaling to the LiDAR | 0.6% | 1.2% |
| 3D point error on the building, median / 90th percentile | 1.51 / 2.37 m | 1.27 / 2.37 m |
| Roof top above the scene's lowest point, each measured in its own pointmap, LiDAR vs MoGe | 4.07 vs 8.02 m | 6.02 vs 13.83 m |

Without LiDAR the reconstruction has no real-world scale, and even at the
LiDAR's scale MoGe's wrong focal length puts points metres out sideways, and
its heights are wrong: measured from its own scene's lowest point, MoGe puts
each roof about twice as high as the LiDAR does. The LiDAR pointmap removes all of this by construction. **These figures measure SAM 3D's
input, not its output.** (An earlier lab note measured the same on photos made
from LINZ's full DSM: 18.7–20.0× and 22–47% off.)

## Results

SAM 3D ran with the official `facebook/sam-3d-objects` weights (all nine
checkpoints' SHA-256 match Hugging Face's LFS ids). It ran on both buildings,
with MoGe depth and with the LiDAR pointmap: seed 42 (the protocol run) and
seeds 1–5. Each run took 5–10 s after an 11–16 s load, at about 19 GB peak
GPU memory on the RTX 5090. Its meshes are scored exactly as Roofer's is.
SAM 3D figures are the median of the six seeds, with the range in brackets.
[`scripts/summarize.py`](scripts/summarize.py) builds the full table from the
score files ([outputs/summary.md](outputs/summary.md); per-run scores in
[outputs/scores/](outputs/scores/)).

| | House, MoGe depth | House, LiDAR pointmap | House, Roofer | Behind trees, MoGe depth | Behind trees, LiDAR pointmap | Behind trees, Roofer |
|---|---|---|---|---|---|---|
| Footprint IoU with the outline | 0.00 | 0.69 (0.61–0.76) | 0.91 | 0.00 | 0.44 (0.39–0.54) | 0.84 |
| Roof error, median, no alignment | no roof over any held-out point | 0.79 m (0.35–1.65) | 0.07 m | no roof over any held-out point | 1.70 m (0.92–2.35) | 0.11 m |
| Same, read straight above each point | — | 0.68 m (0.32–1.44) | 0.03 m | — | 1.59 m (0.80–2.26) | 0.05 m |
| Roof height, model less held-out | +24.1 m | +1.0 m (0.5–2.0) | +0.09 m | +23.5 m | +1.9 m (0.9–3.2) | −0.09 m |
| Scale the alignment needed | 22.2× (21.5–22.9) | 0.85 (0.80–0.87) | 0.96 | 16.9× (16.1–18.9) | 0.69 (0.63–0.74) | 1.01 |
| Roof error after alignment (condition 3), median | 0.41 m (0.34–0.48) | 0.39 m (0.35–0.53) | 0.15 m | 0.46 m (0.38–0.57) | 0.46 m (0.36–0.55) | 0.21 m |
| Closed solids | 3 of 6 | 3 of 6 | yes | 5 of 6 | 4 of 6 | yes |

[outputs/heights_b6.png](outputs/heights_b6.png) and
[outputs/heights_b3.png](outputs/heights_b3.png) show the seed-42 models
from above against the training-points DSM
([`render_heights.py`](scripts/render_heights.py)).

**What it shows:**

- **Without LiDAR, SAM 3D has no real-world scale.** Its model is 17–22×
  too small and sits about 24 m off, near the camera, covering none of the
  outline. That is what the MoGe check predicted: MoGe's raw depth is 19.9×
  too small.
- **The LiDAR pointmap fixes placement and scale, not shape.** With it, the
  model stands on the building (IoU 0.69 house, 0.44 behind trees), but its
  roof is 0.7–1.7 m too high and its footprint too big. The footprint's
  principal lengths are 1.31 and 1.15 times the outline's on the house,
  1.69 and 1.35 behind the trees. After the best alignment, the roof is no
  better than without LiDAR (0.39 against 0.41 m on the house, 0.46 against
  0.46 m behind the trees). The spread across seeds (0.34–0.57 m) is larger
  than either difference.
- **Explicit fitting (condition 3) adds placement, not accuracy.** It
  removes the scale and position error, but leaves 0.4–0.5 m of roof error.
  Roofer's own model scores 0.15 and 0.21 m on the same alignment.
- **Roofer is about ten times as accurate.** From the same training points,
  its roofs are 7–11 cm from the held-out points (3–5 cm straight above),
  against 0.8–1.7 m for SAM 3D with LiDAR. Its footprints match better
  (0.91 and 0.84), and both its models are closed solids.
- **Over a third of the SAM 3D meshes aren't valid solids.** Only 3–5 of
  each six are closed (every edge on two faces; 15 of 24 in all), and they are 320,000–620,000-triangle
  surfaces with no roof planes.
- **The Gaussians agree with the mesh on seed 42**, the only seed whose
  Gaussians were scored (`sam3d-*-gaussians.json`, a secondary record). For
  example, on the house with LiDAR, seed 42 gives: IoU 0.65 against the
  mesh's 0.62, and roof after alignment 0.47 against 0.45 m.

**Decision: LiDAR-conditioned SAM 3D models don't go into the app's 3D
view.**
- The view already stands buildings at their measured LiDAR footprints and
  heights.
- SAM 3D with LiDAR would put roofs 0.7–1.7 m off and footprints 15–70% too
  big. That is about ten times worse than Roofer from the same points.
- Its roof shape after alignment is no better than with no LiDAR at all, and
  5 of its 12 meshes aren't valid solids.

If the 3D view ever needs roof form, Roofer on the LiDAR points is the method
to evaluate, not a generative model.

**Limits of this result:** two buildings in one scene, from synthetic
oblique photos (an orthophoto draped on a 1 m surface, with smeared walls),
scored against LINZ's 2020–22 LiDAR. It says nothing about SAM 3D on real
oblique photography.

## Example inputs and outputs

- [`inputs/`](inputs/): for each building (`b6`, the house; `b3`, the
  building behind trees), the virtual oblique photo, its mask over it, and
  MoGe's depth error against the LiDAR pointmap, with the numbers.
- [`outputs/`](outputs/): Roofer's LoD 2.2 models, every run's scores
  (seed 42 in `scores/`, seeds 1–5 in `scores/seeds/`), the results table
  (`summary.md`) and the height maps (`heights_b6.png`, `heights_b3.png`).
- **SAM 3D's models aren't committed.** Each run's mesh (`mesh.npz`, about
  20 MB, 320,000–620,000 triangles), splat (`splat.ply`, about 22 MB) and
  Gaussian centres (`scene_points.npy`) are too big. They live in
  `~/src/button-nz-results/sam3d-spike/train-{b6,b3}/{moge,lidar}/` (seed 42)
  and `.../seeds/train-{b6,b3}-s{1..5}/{moge,lidar}/`. To remake them, run
  [`get_weights_and_run.sh`](scripts/get_weights_and_run.sh) for seed 42.
  For the other seeds, run `run_sam3d.py REPO SCENE_DIR SEED` on a copy of
  each building's scene directory.

All imagery comes from LINZ open data (aerial photos and LiDAR, CC BY 4.0).
No supplier or third-party imagery is used.

## How to run it

The setup lives outside the repo, in `~/src/sam3d-spike/`. Its weights and
third-party code are untrusted downloads, kept apart from the project.

1. Request access at https://huggingface.co/facebook/sam-3d-objects (the
   owner, with a Hugging Face account; granted for this run).
2. Once approved: `~/src/sam3d-spike/env/bin/hf auth login`.
3. `~/src/sam3d-spike/scripts/get_weights_and_run.sh`
   ([copy](scripts/get_weights_and_run.sh)). It downloads the weights, runs
   SAM 3D with MoGe depth and with the LiDAR pointmap on both buildings'
   training-points scenes (GPU 1), and scores both, with condition 3 as the
   scorer's alignment, into `scores/`: `sam3d-{moge,lidar}-{b6,b3}.json` from
   SAM 3D's mesh, and `...-gaussians.json` from its active Gaussian centres.

The scripts here are copies of the ones run, kept with the results. They
run in their own environments (`scripts/pyproject.toml` for the split and
scoring; the SAM 3D env and Blender for the rest), not the app's.

**The environment, and why it isn't upstream's:**
- Upstream's setup pins torch 2.5.1/cu121, which has no kernels for the
  RTX 5090.
- The working environment is a micromamba env with Python 3.11, torch
  2.8.0+cu128 and CUDA 12.8 (built with gcc 12).
- pytorch3d, kaolin and gsplat are built from source for the 5090.
- SAM 3D asks for at least 32 GB of VRAM; it peaked at about 19 GB here.
  GPU 0 is taken by another service, so it runs on GPU 1.

## Risks and limits

- **Smeared walls:** the virtual photo's walls are smeared. The DSM is 1 m
  and the aerial looks straight down, so roofs look right but walls are
  partly invented. SAM 3D's training on everyday objects may not suit
  buildings.
- **Not the measured footprint:** the app's 3D view already stands buildings
  at their LiDAR heights. SAM 3D would mainly add believable surfaces and
  form, so it isn't a replacement for the measured footprint and heights the
  evaluator uses, and never will be.
- **The truth is dated:** LINZ outlines are from 2015–16 and nothing
  independent checks them. A footprint comparison measures against them, not
  against ground truth.

Tracked in [#125](https://github.com/gardner/button-nz/issues/125).
