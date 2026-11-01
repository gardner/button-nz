# Experiment: SAM 3D Objects conditioned on LiDAR

**Status:** ready to run, waiting for model access. SAM 3D's weights on
Hugging Face (`facebook/sam-3d-objects`) are gated, and Meta approves access
by hand. Everything else is installed and tested on this machine's RTX 5090.

## The question

Can Meta's SAM 3D Objects reconstruct a real house from aerial photography,
and does giving it measured LiDAR, instead of its own estimate of depth, make
that reconstruction accurate?

SAM 3D Objects turns a masked object in a photo into a 3D model: shape,
texture and pose. Its geometry model can take an optional **scene pointmap**:
a 3D point for every pixel. The paper says this can come "from hardware
sensors (e.g., LiDAR on an iPhone)" ([SAM 3D, arXiv 2511.16624](https://arxiv.org/abs/2511.16624)),
but its results use depth estimated from the image itself.

As far as we know, nobody has fed it survey LiDAR.

- SAM 3D has been run on remote-sensing images from the image alone
  ([arXiv 2512.22452](https://arxiv.org/abs/2512.22452)), judged by FID
  only, with no measured ground truth.
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
4. **Two runs of SAM 3D on the same photo and mask:**
   - **without LiDAR,** where SAM 3D estimates depth itself (MoGe);
   - **with LiDAR,** passing our pointmap.
5. **Measure each reconstruction against the truth we have:**
   - roof height against the nDSM;
   - footprint against the LINZ outline (overlap, IoU);
   - overall scale.

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

## What we've measured so far: the depth input

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
- [`outputs/`](outputs/): for each building, SAM 3D's model with and without
  LiDAR (rendered views, plus the mesh or splat), and the measurements beside
  the truth.

All imagery comes from LINZ open data (aerial photos and LiDAR, CC BY 4.0).
No supplier or third-party imagery is used.

## How to run it

The setup lives outside the repo, in `~/src/sam3d-spike/`. Its weights and
third-party code are untrusted downloads, kept apart from the project.

1. Request access at https://huggingface.co/facebook/sam-3d-objects (the
   owner, with a Hugging Face account).
2. Once approved: `~/src/sam3d-spike/env/bin/hf auth login`.
3. `~/src/sam3d-spike/scripts/get_weights_and_run.sh`. It downloads the
   weights, then runs both conditions for both buildings on GPU 1.

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
