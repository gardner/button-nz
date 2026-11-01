"""Roofer's inputs from the split: train.laz (training points only) and the
target outlines (footprints.geojson, NZTM). The LAZ carries NZTM2000 + NZVD2016 height. usage: roofer_inputs.py SPIKE_DIR"""
import json, sys
from pathlib import Path
import laspy, numpy as np
spike = Path(sys.argv[1]); out = spike / "roofer"; out.mkdir(exist_ok=True)
pts = np.load(spike / "split" / "points.npz")["train"]
h = laspy.LasHeader(point_format=1, version="1.4"); h.scales = [0.01, 0.01, 0.001]; h.offsets = pts[:, :3].min(axis=0)
h.add_crs(__import__("pyproj").CRS.from_user_input("EPSG:2193+7839"), keep_compatibility=False)  # WKT: GeoTIFF keys cannot hold it
las = laspy.LasData(h); las.x, las.y, las.z = pts[:, 0], pts[:, 1], pts[:, 2]
las.classification = pts[:, 3].astype(np.uint8); las.write(out / "train.laz")
features = []
for name in ("b6", "b3"):
    o = json.loads((spike / f"train-{name}" / "outline.json").read_text())
    features.append({"type": "Feature", "properties": {"bid": name}, "geometry": o["target"]})
(out / "footprints.geojson").write_text(json.dumps({"type": "FeatureCollection",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2193"}}, "features": features}))
print(len(pts), "training points;", len(features), "outlines")
