# Experiment C: autonomous Blender design

Model `muse-spark-1.3` (reasoning effort max); 3 briefs x 2 repeats per condition. Each run is the design loop on the demo site: sandboxed Blender builds each attempt and the independent evaluator checks it. Accepted means no check failed on the final attempt; repair rate is over runs whose first attempt failed or errored. Under `errors` the model hears only execution errors, so a script that runs ends the run; an incomplete run keeps the attempts that finished.

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| evaluator_lidar | 6 | 5 (83%) | 70% | 67% | 1.7 | 4.0 | 446.5 | 0 |

## Incomplete runs

None.
