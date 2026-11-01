# Experiment: SAM 3D Objects conditioned on LiDAR

**Status:** everything but SAM 3D itself is built and measured; SAM 3D is
waiting for model access.

- **Done:**
  - **Held-out truth:** LINZ's raw LAS/LAZ points for the scene, split into
    held-out blocks and training points, with a DSM and DEM made from the
    training points alone ([below](#held-out-truth)).
  - **Inputs remade from the training points:** both buildings' oblique
    photos, pointmaps and masks ([inputs/](inputs/)).
  - **The scorer**, shape and layout, self-tested on known distortions
    ([below](#the-scorer)).
  - **Condition 4, Roofer**, run and scored: its roofs sit 7–11 cm (median)
    from the held-out points ([below](#condition-4-roofer)).
  - **Condition 3, the fitted model**, is the scorer's alignment (fitted to
    the training points), so it's scored with condition 2.
- **Blocked:** SAM 3D's weights on Hugging Face (`facebook/sam-3d-objects`)
  are gated, and Meta approves access by hand. Once approved, one script
  runs and scores conditions 1–3 ([How to run it](#how-to-run-it)).
- **Not yet measured:** roof-plane topology (Roofer reports its own planes;
  SAM 3D's splats have none to count).

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

### How the pointmap goes in (verified in the code, not yet run)

- **Call path:** `Inference.__call__(image, mask, seed, pointmap=...)` in
  `notebook/inference.py`, then `InferencePipelinePointMap.run(pointmap=...)`,
  then `compute_pointmap()` in
  `sam3d_objects/pipeline/inference_pipeline_pointmap.py`. With no pointmap
  given, it runs MoGe instead.
- **Format:** an H×W×3 float tensor in PyTorch3D camera coordinates (x left,
  y up, z forward: OpenCV's with x and y negated). Missing pixels may be NaN.
- **Scale:** the pipeline normalises scale and restores it on the output, so
  metric LiDAR should give a metric model.

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
  training cells around them. Against LINZ's own rasters, the DEM differs by
  2 cm (median) and the DSM by 5 cm (median; 1.2 m at the 90th percentile,
  at trees and edges, where LINZ's DSM carries the held-out points).
- **Every input is made from these:** the photos, pointmaps and masks
  ([`prep.py`](scripts/prep.py) with the training surfaces, then
  [`render_oblique.py`](scripts/render_oblique.py) and
  [`mask.py`](scripts/mask.py)); Roofer gets the training points themselves
  ([`roofer_inputs.py`](scripts/roofer_inputs.py)). The pointmap reprojects
  to its own pixel within 0.0007 px.

## The scorer

[`scripts/score.py`](scripts/score.py) reduces every model to points on its
surface (a mesh sampled at 25 per m²; SAM 3D's Gaussian centres as they
are), in the site's local frame, then measures:

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

**Self-test** ([`scripts/selftest.py`](scripts/selftest.py)): Roofer's model
of the house, as points, distorted on purpose. Layout catches each
distortion; shape is the same after alignment, whatever the distortion, so
it measures shape alone:

| Distortion | Roof median, no alignment | Footprint IoU | Fitted scale | Roof median, after alignment |
|---|---|---|---|---|
| None | 0.07 m | 0.90 | 0.95 | 0.15 m |
| Moved 3 m east, 1 m up | 0.87 m | 0.54 | 0.95 | 0.15 m |
| Turned 10°, 1.2× | 0.49 m | 0.64 | 0.78 | 0.15 m |
| 20× too big (as MoGe's depth is) | 37.4 m | 0.02 | 0.048 | 0.15 m |

**The alignment's floor is 0.15 m:** an undistorted model loses 8 cm to it,
because the 1 m roof cells it fits to sit just inside the outline (fitted
scale 0.95). Compare shape numbers with each other and with that floor, not
with the layout numbers. Footprint and scale carry about one 0.5 m cell of
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
| Roof error after alignment, median / RMSE | 0.15 / 0.25 m | 0.20 / 0.21 m |
| Valid closed solid | yes (24 triangles) | yes (36 triangles) |

A conventional method, given the same training points, gets roofs within
about 10 cm. Roofer reported 42% of each roof as no-data: the held-out
blocks. That's the bar for SAM 3D with the LiDAR pointmap.

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

## Example inputs and outputs

- [`inputs/`](inputs/): for each building (`b6`, the house; `b3`, the
  building behind trees), the virtual oblique photo, its mask over it, and
  MoGe's depth error against the LiDAR pointmap, with the numbers.
- [`outputs/`](outputs/): Roofer's LoD 2.2 models and every condition's
  scores. SAM 3D's models go here after the run.

All imagery comes from LINZ open data (aerial photos and LiDAR, CC BY 4.0).
No supplier or third-party imagery is used.

## How to run it

The setup lives outside the repo, in `~/src/sam3d-spike/`. Its weights and
third-party code are untrusted downloads, kept apart from the project.

1. Request access at https://huggingface.co/facebook/sam-3d-objects (the
   owner, with a Hugging Face account).
2. Once approved: `~/src/sam3d-spike/env/bin/hf auth login`.
3. `~/src/sam3d-spike/scripts/get_weights_and_run.sh`
   ([copy](scripts/get_weights_and_run.sh)). It downloads the weights, runs
   SAM 3D with MoGe depth and with the LiDAR pointmap on both buildings'
   training-points scenes (GPU 1), and scores both, with condition 3 as the
   scorer's alignment, into `scores/`.

The scripts here are copies of the ones run, kept with the results. They
run in their own environments (`scripts/pyproject.toml` for the split and
scoring; the SAM 3D env and Blender for the rest), not the app's.

**The environment, and why it isn't upstream's:**
- Upstream's setup pins torch 2.5.1/cu121, which has no kernels for the
  RTX 5090.
- The working environment is a micromamba env with Python 3.11, torch
  2.8.0+cu128 and CUDA 12.8 (built with gcc 12).
- pytorch3d, kaolin and gsplat are built from source for the 5090.
- SAM 3D asks for at least 32 GB of VRAM. GPU 0 is taken by another service,
  so it runs on GPU 1.

## Risks and limits

- **Model access:** approval is manual and may not arrive before the
  5 November deadline.
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
