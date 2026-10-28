# Experiment A: understanding LiDAR

Model `muse-spark-1.3`; 47 questions (seed 2026), each asked under every condition and scored against answers computed from the LiDAR DEM and nDSM (`button_nz.bench.questions`). Replies without an answer count as wrong. The `agent` condition can also make numeric queries (elevation statistics over an area, cross-sections) that no fixed map gives, so its gain over `fixed_all` measures active observation with numbers, not view choice alone.

| Condition | n | Correct | Accuracy | No answer | Mean s |
|---|---|---|---|---|---|
| aerial | 47 | 25 | 53% | 0 | 24.4 |
| aerial_contours | 47 | 27 | 57% | 0 | 36.3 |
| aerial_ndsm_slope | 47 | 26 | 55% | 0 | 20.0 |
| fixed_all | 47 | 28 | 60% | 0 | 27.5 |
| agent | 47 | 33 | 70% | 14 | 20.4 |

## Observations the model chose

- agent: inspect_elevation x68, render_contours x9, render_cross_section x14, render_height_map x9, render_hillshade x9

## By kind (correct / n)

| Condition | aspect | height_difference | relief | steepest | tallest |
|---|---|---|---|---|---|
| aerial | 8/10 | 2/10 | 1/10 | 7/10 | 7/7 |
| aerial_contours | 8/10 | 3/10 | 2/10 | 9/10 | 5/7 |
| aerial_ndsm_slope | 9/10 | 0/10 | 2/10 | 9/10 | 6/7 |
| fixed_all | 9/10 | 3/10 | 1/10 | 8/10 | 7/7 |
| agent | 7/10 | 8/10 | 7/10 | 10/10 | 1/7 |

## Wrong answers

- `aspect-3` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `aspect-4` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `aspect-5` (aerial): answered `SE`
- `aspect-5` (aerial_contours): answered `S`
- `aspect-5` (aerial_ndsm_slope): answered `SW`
- `aspect-5` (fixed_all): answered `S`
- `aspect-5` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `aspect-7` (aerial_contours): answered `SW`
- `aspect-10` (aerial): answered `SW`
- `height_difference-1` (aerial): answered `1.2`
- `height_difference-1` (aerial_contours): answered `2`
- `height_difference-1` (aerial_ndsm_slope): answered `1`
- `height_difference-2` (aerial): answered `2.1`
- `height_difference-2` (aerial_contours): answered `1.5`
- `height_difference-2` (aerial_ndsm_slope): answered `1`
- `height_difference-2` (fixed_all): answered `1.5`
- `height_difference-3` (aerial): answered `0.3`
- `height_difference-3` (aerial_contours): answered `1.5`
- `height_difference-3` (aerial_ndsm_slope): answered `0.5`
- `height_difference-4` (aerial): answered `-1`
- `height_difference-4` (aerial_contours): answered `-2`
- `height_difference-4` (aerial_ndsm_slope): answered `-1`
- `height_difference-4` (fixed_all): answered `-2`
- `height_difference-5` (aerial): answered `-1`
- `height_difference-5` (aerial_contours): answered `-2`
- `height_difference-5` (aerial_ndsm_slope): answered `-2`
- `height_difference-5` (fixed_all): answered `-1`
- `height_difference-5` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `height_difference-6` (aerial): answered `0.9`
- `height_difference-6` (aerial_ndsm_slope): answered `1.2`
- `height_difference-6` (fixed_all): answered `1`
- `height_difference-6` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `height_difference-7` (aerial): answered `0.5`
- `height_difference-7` (aerial_ndsm_slope): answered `0.5`
- `height_difference-7` (fixed_all): answered `0.5`
- `height_difference-8` (aerial): answered `0.9`
- `height_difference-8` (aerial_contours): answered `0.4`
- `height_difference-8` (aerial_ndsm_slope): answered `2`
- `height_difference-8` (fixed_all): answered `1`
- `height_difference-9` (aerial_contours): answered `-1`
- `height_difference-9` (aerial_ndsm_slope): answered `-0.7`
- `height_difference-10` (aerial_ndsm_slope): answered `0`
- `height_difference-10` (fixed_all): answered `0`
- `relief-1` (aerial): answered `0.5`
- `relief-1` (aerial_contours): answered `0.5`
- `relief-1` (aerial_ndsm_slope): answered `1`
- `relief-1` (fixed_all): answered `1.25`
- `relief-2` (aerial): answered `0.5`
- `relief-2` (aerial_contours): answered `0.75`
- `relief-2` (aerial_ndsm_slope): answered `1`
- `relief-2` (fixed_all): answered `1.5`
- `relief-3` (aerial): answered `0.6`
- `relief-3` (aerial_contours): answered `0.5`
- `relief-3` (aerial_ndsm_slope): answered `0.6`
- `relief-3` (fixed_all): answered `0.9`
- `relief-3` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `relief-4` (aerial): answered `0.8`
- `relief-4` (aerial_ndsm_slope): answered `1`
- `relief-4` (fixed_all): answered `1`
- `relief-5` (aerial_ndsm_slope): answered `0`
- `relief-5` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `relief-6` (aerial): answered `0.5`
- `relief-6` (aerial_contours): answered `0.5`
- `relief-6` (aerial_ndsm_slope): answered `1`
- `relief-6` (fixed_all): answered `1`
- `relief-7` (aerial): answered `0.6`
- `relief-7` (aerial_contours): answered `0.5`
- `relief-7` (fixed_all): answered `0.5`
- `relief-8` (aerial): answered `0.6`
- `relief-8` (aerial_contours): answered `1`
- `relief-8` (aerial_ndsm_slope): answered `1`
- `relief-8` (fixed_all): answered `1`
- `relief-8` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `relief-9` (aerial): answered `0.5`
- `relief-9` (aerial_contours): answered `0.5`
- `relief-9` (aerial_ndsm_slope): answered `1`
- `relief-9` (fixed_all): answered `1`
- `relief-10` (aerial): answered `0.5`
- `relief-10` (aerial_contours): answered `0.25`
- `relief-10` (fixed_all): answered `0.5`
- `steepest-1` (aerial): answered `3`
- `steepest-1` (aerial_ndsm_slope): answered `3`
- `steepest-1` (fixed_all): answered `3`
- `steepest-3` (aerial): answered `3`
- `steepest-6` (aerial): answered `1`
- `steepest-8` (fixed_all): answered `1`
- `steepest-9` (aerial_contours): answered `1`
- `tallest-1` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-2` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-3` (aerial_ndsm_slope): answered `2`
- `tallest-3` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-4` (aerial_contours): answered `2`
- `tallest-4` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-6` (aerial_contours): answered `1`
- `tallest-6` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-7` (agent): answered `None`; The reply did not call submit_answer with an answer.
