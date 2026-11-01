# Experiment: SAM 3D Objects conditioned on LiDAR

**Status:** partly built, waiting for model access.

- **Done:** SAM 3D's environment is installed and tested on this machine's
  RTX 5090. The virtual oblique photos, pointmaps and masks are made for two
  buildings. The MoGe-vs-LiDAR check on the depth input is measured.
- **Blocked:** SAM 3D's weights on Hugging Face (`facebook/sam-3d-objects`)
  are gated, and Meta approves access by hand.
- **Still to build:**
  - the held-out truth: LINZ's LAS/LAZ points, with an input surface made
    without the held-out ones (step 6);
  - the fitting step (condition 3);
  - Roofer (condition 4);
  - the shape and layout scoring (step 5).

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
   - The pointmap comes from the 1 m DSM, and LINZ makes that DSM from its
     LAS/LAZ points. So scoring against the DSM, or against all those
     points, only tests how faithfully the model follows its input:
     **source-data fidelity**, reported as such.
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

## What we've measured so far: the depth input

**Not yet reproducible from this repo.** These figures were recorded by hand
from the spike's scripts in `~/src/sam3d-spike/scripts/` (`render_oblique.py`,
`mask.py`, `moge_check.py`), which aren't committed yet. They'll be committed
with the run (#125), as `docs/results` experiments are, with the commit
named. Until then, treat this table as a lab note.

SAM 3D hasn't run yet. What we could measure is the depth it would use
without LiDAR: MoGe (`Ruicheng/moge-vitl`) on our virtual oblique photos,
compared with the exact LiDAR pointmap. Two buildings at 1 Victory Street,
Reefton:

| | House (179 m², clear view) | Building behind trees (155 m²) |
|---|---|---|
| MoGe's raw scale vs metric | 18.7× too small | 20.0× too small |
| Focal length, true vs MoGe | 996 vs 1,468 px (47% off) | 996 vs 1,214 px (22% off) |
| Depth error on the building, after scaling to the LiDAR | 0.5% | 0.6% |
| 3D point error on the building, median / 90th percentile | 1.74 / 2.73 m | 1.06 / 1.66 m |
| Roof top above the scene's lowest point, LiDAR vs MoGe | 4.05 vs 3.50 m | 4.62 vs 4.20 m |

Without LiDAR, the reconstruction has no real-world scale. Even after taking
the LiDAR's scale, MoGe's wrong focal length puts points metres out sideways.
The LiDAR pointmap removes both errors by construction.

**These figures measure the input SAM 3D would get, not SAM 3D's output.**
They hold whatever the meshes turn out like.

## Example inputs and outputs

To be added after the run:

- [`inputs/`](inputs/): for each building, the virtual oblique photo, its
  mask over it, the LiDAR pointmap (as a depth image), and MoGe's depth error.
- [`outputs/`](outputs/): for each building, the four conditions' models
  (rendered views, plus the mesh or splat), with the shape and layout
  measurements beside the held-out truth.

All imagery comes from LINZ open data (aerial photos and LiDAR, CC BY 4.0).
No supplier or third-party imagery is used.

## How to run it

The setup lives outside the repo, in `~/src/sam3d-spike/`. Its weights and
third-party code are untrusted downloads, kept apart from the project.

1. Request access at https://huggingface.co/facebook/sam-3d-objects (the
   owner, with a Hugging Face account).
2. Once approved: `~/src/sam3d-spike/env/bin/hf auth login`.
3. `~/src/sam3d-spike/scripts/get_weights_and_run.sh`. It downloads the
   weights, then runs the first two conditions (MoGe depth, and the LiDAR
   pointmap) for both buildings on GPU 1. It doesn't yet make the held-out
   surface, the fitted condition, Roofer or the scoring: those are still to
   build (see Status).

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
