# Experiment C: autonomous Blender design

Model `muse-spark-1.3`; 3 briefs x 2 repeats per condition. Each run is the design loop on the demo site: sandboxed Blender builds each attempt and the independent evaluator checks it. Accepted means no check failed on the final attempt; repair rate is over runs whose first attempt failed or errored. Under `errors` the model hears only execution errors, so a script that runs ends the run; an incomplete run keeps the attempts that finished.

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| one_shot | 6 | 4 (67%) | 83% | 0% | 1.0 | 0.0 | 44.3 | 0 |
| errors | 6 | 5 (83%) | 100% | 0% | 1.0 | 0.0 | 39.4 | 0 |
| evaluator | 6 | 6 (100%) | 89% | 100% | 1.5 | 0.0 | 58.0 | 0 |
| evaluator_lidar | 6 | 6 (100%) | 80% | 100% | 1.7 | 4.0 | 205.8 | 0 |

## Incomplete runs

None.
