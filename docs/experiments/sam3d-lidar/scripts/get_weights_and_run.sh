#!/usr/bin/env bash
# After HF access to facebook/sam-3d-objects is granted and `hf auth login` is done:
# runs SAM 3D (MoGe depth, and the LiDAR pointmap) on the training-points scenes,
# then scores every condition against the held-out points (#125).
set -euxo pipefail
SPIKE=/home/gardner/src/sam3d-spike
REPO=$SPIKE/repo/sam-3d-objects
OUT=/home/gardner/src/button-nz-results/sam3d-spike
export CONDA_PREFIX=$SPIKE/env PATH=$SPIKE/env/bin:$PATH CUDA_HOME=$SPIKE/env HF_HOME=$SPIKE/hf CUDA_VISIBLE_DEVICES=1
if [ ! -f $REPO/checkpoints/hf/pipeline.yaml ]; then
  $SPIKE/env/bin/hf download --repo-type model --local-dir $SPIKE/dl/sam3d-weights --max-workers 1 facebook/sam-3d-objects
  mkdir -p $REPO/checkpoints && ln -sfn $SPIKE/dl/sam3d-weights/checkpoints $REPO/checkpoints/hf
fi
cd $SPIKE/scripts
for b in b6 b3; do
  $SPIKE/env/bin/python -I run_sam3d.py $REPO $OUT/train-$b 42
done
cd $SPIKE/eval
mkdir -p $OUT/scores
for b in b6 b3; do
  for c in moge lidar; do
    uv run python -I score.py $OUT $b $OUT/train-$b/$c/scene_points.npy > $OUT/scores/sam3d-$c-$b.json
  done
done
