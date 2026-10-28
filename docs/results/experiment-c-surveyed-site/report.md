# Experiment C: autonomous Blender design

Model `muse-spark-1.3`; 3 briefs x 3 repeats per condition. Each run is the design loop on the surveyed site (its features decided by the Button NZ team, from the aerial photo and the LiDAR, pending the owner's confirmation): sandboxed Blender builds each attempt and the independent evaluator checks it. Accepted means no check failed on the final attempt; repair rate is over runs whose first attempt failed or errored. Under `errors` the model hears only execution errors, so a script that runs ends the run; an incomplete run keeps the attempts that finished.

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| one_shot | 9 | 5 (56%) | 100% | 0% | 1.0 | 0.0 | 74.2 | 0 |
| errors | 9 | 6 (67%) | 100% | 0% | 1.0 | 0.0 | 123.3 | 0 |
| evaluator | 9 | 9 (100%) | 100% | 100% | 1.6 | 0.0 | 110.8 | 0 |
| evaluator_lidar | 9 | 9 (100%) | 100% | 100% | 1.4 | 3.9 | 160.9 | 0 |

## Incomplete runs

None.
