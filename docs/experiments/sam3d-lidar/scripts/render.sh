#!/usr/bin/env bash
# render.sh NAME AZIMUTH PITCH DISTANCE
set -euo pipefail
blender -b --factory-startup --python-exit-code 1 -P /home/gardner/src/sam3d-spike/scripts/render_oblique.py -- \
  /home/gardner/src/button-nz-results/sam3d-spike/"$1" \
  /home/gardner/src/button-nz-results/owner-review/sites/1-victory-street-reefton/aerial.png "$2" "$3" "$4" 2>&1 | grep RAYCAST
