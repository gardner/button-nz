# Example outputs

- `roofer/`: Roofer 1.0.0's LoD 2.2 models (CityJSONSeq, NZTM; the transform is in `metadata.json`), condition 4.
  They are Roofer's files as it wrote them, kept unedited as the record of the run. Two things in `metadata.json` are Roofer's own and not right: `referenceSystem` names EPSG:2193 alone, though its input LAZ carried NZTM2000 + NZVD2016 (EPSG:2193+7839) and the heights are NZVD2016; and `geographicalExtent` gives z as 0 to 0, though the roofs run from about 185.8 to 190.7 m (each feature's own attributes have the true heights).
- `scores/`: each condition's scores from `scripts/score.py`, per building.
- `surfaces-vs-linz.json`: the training-points DSM and DEM against LINZ's own rasters, from `scripts/check_surfaces.py`.

SAM 3D's models (conditions 1–3) go here after the run.
