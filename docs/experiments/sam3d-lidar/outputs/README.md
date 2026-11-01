# Example outputs

To be added after the run (#125). For each building, one model per condition (rendered views, and the mesh, splat or LoD2 model):

1. SAM 3D with its own MoGe depth;
2. SAM 3D with the LiDAR pointmap;
3. SAM 3D with the LiDAR pointmap, then fitted to the training points;
4. Roofer, from the training points and the outline.

Beside them, the shape measures (after the best alignment) and the layout measures (with none), against the held-out points.
