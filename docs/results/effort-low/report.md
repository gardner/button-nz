# Experiment C: autonomous Blender design

Model `muse-spark-1.3` (reasoning effort low); 3 briefs x 1 repeats per condition. Each run is the design loop on the demo site, with no confirmed buildings or keep-clear areas: sandboxed Blender builds each attempt and the independent evaluator checks it. Accepted means no check failed on the final attempt; repair rate is over runs whose first attempt failed or errored. Under `errors` the model hears only execution errors, so a script that runs ends the run; an incomplete run keeps the attempts that finished. A script call is one model call that wrote a script, timed from asking to the reply.

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Mean s per script call | Incomplete |
|---|---|---|---|---|---|---|---|---|---|
| evaluator_lidar | 3 | 1 (33%) | 50% | 33% | 2.7 | 4.0 | 177.9 | 38.8 | 0 |

## Incomplete runs

None.
