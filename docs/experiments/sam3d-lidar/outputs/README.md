# Example outputs

- `roofer/`: Roofer 1.0.0's LoD 2.2 models (CityJSONSeq, NZTM; the transform is in `metadata.json`), condition 4.
  They are Roofer's files as it wrote them, kept unedited as the record of the run. Two things in `metadata.json` are Roofer's own and not right: `referenceSystem` names EPSG:2193 alone, though its input LAZ carried NZTM2000 + NZVD2016 (EPSG:2193+7839) and the heights are NZVD2016; and `geographicalExtent` gives z as 0 to 0, though the roofs run from about 185.8 to 190.7 m (each feature's own attributes have the true heights).
- `scores/`: each condition's scores from `scripts/score.py`, per building.
- `surfaces-vs-linz.json`: the training-points DSM and DEM against LINZ's own rasters, from `scripts/check_surfaces.py`.

- `scores/sam3d-{moge,lidar}-{b6,b3}.json`: SAM 3D's mesh scored, seed 42; `...-gaussians.json`: its active Gaussian centres, a secondary record; `scores/seeds/`: seeds 1–5.
- `summary.md`: the results table, from `scripts/summarize.py outputs/scores`.
- `heights_b6.png`, `heights_b3.png`: every seed-42 model seen from above against the training-points DSM, from `scripts/render_heights.py`.

SAM 3D's meshes and splats are too big to commit; the experiment README says where they are and how to remake them.
