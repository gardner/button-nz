# Experiment A: understanding LiDAR

Model `muse-spark-1.3`; 47 questions (seed 2026), each asked under every condition and scored against answers computed from the LiDAR DEM and nDSM (`button_nz.bench.questions`). A reply that doesn't call the answer tool gets one reminder (the API can't require the tool); a second counts as no answer, and wrong. The `agent` condition can also make numeric queries (elevation statistics over an area, cross-sections) that no fixed map gives, so its gain over `fixed_all` measures active observation with numbers, not view choice alone.

| Condition | n | Correct | Accuracy | No answer | Mean s |
|---|---|---|---|---|---|
| aerial | 47 | 23 | 49% | 0 | 23.8 |
| aerial_contours | 47 | 26 | 55% | 0 | 39.7 |
| aerial_ndsm_slope | 47 | 27 | 57% | 0 | 20.5 |
| fixed_all | 47 | 31 | 66% | 0 | 27.9 |
| agent | 47 | 39 | 83% | 7 | 14.9 |

## Observations the model chose

- agent: inspect_elevation x70, render_contours x9, render_cross_section x17, render_height_map x8, render_hillshade x4

## By kind (correct / n)

| Condition | aspect | height_difference | relief | steepest | tallest |
|---|---|---|---|---|---|
| aerial | 9/10 | 2/10 | 1/10 | 5/10 | 6/7 |
| aerial_contours | 8/10 | 4/10 | 2/10 | 7/10 | 5/7 |
| aerial_ndsm_slope | 9/10 | 2/10 | 2/10 | 8/10 | 6/7 |
| fixed_all | 9/10 | 3/10 | 3/10 | 9/10 | 7/7 |
| agent | 8/10 | 10/10 | 7/10 | 10/10 | 4/7 |

## Wrong answers

- `aspect-5` (aerial): answered `SW`
- `aspect-5` (aerial_contours): answered `S`
- `aspect-5` (aerial_ndsm_slope): answered `S`
- `aspect-5` (fixed_all): answered `S`
- `aspect-5` (agent): answered `N`
- `aspect-7` (aerial_contours): answered `SW`
- `aspect-8` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `height_difference-1` (aerial): answered `0.6`
- `height_difference-1` (aerial_ndsm_slope): answered `1`
- `height_difference-2` (aerial): answered `1.5`
- `height_difference-2` (aerial_contours): answered `1`
- `height_difference-2` (aerial_ndsm_slope): answered `2`
- `height_difference-2` (fixed_all): answered `1`
- `height_difference-3` (aerial): answered `0.5`
- `height_difference-3` (aerial_contours): answered `0.75`
- `height_difference-3` (aerial_ndsm_slope): answered `0.8`
- `height_difference-4` (aerial): answered `-1`
- `height_difference-4` (aerial_contours): answered `-1`
- `height_difference-4` (aerial_ndsm_slope): answered `-1`
- `height_difference-4` (fixed_all): answered `-1`
- `height_difference-5` (aerial): answered `-1.2`
- `height_difference-5` (aerial_contours): answered `-1`
- `height_difference-5` (aerial_ndsm_slope): answered `-1`
- `height_difference-5` (fixed_all): answered `-1.5`
- `height_difference-6` (aerial): answered `0.9`
- `height_difference-6` (aerial_ndsm_slope): answered `1`
- `height_difference-6` (fixed_all): answered `1`
- `height_difference-7` (aerial): answered `0.5`
- `height_difference-7` (aerial_contours): answered `0.75`
- `height_difference-7` (fixed_all): answered `1.5`
- `height_difference-8` (aerial): answered `1.2`
- `height_difference-8` (aerial_contours): answered `2`
- `height_difference-8` (aerial_ndsm_slope): answered `2`
- `height_difference-8` (fixed_all): answered `1`
- `height_difference-9` (fixed_all): answered `-1`
- `height_difference-10` (aerial_ndsm_slope): answered `-0.8`
- `relief-1` (aerial): answered `0.5`
- `relief-1` (aerial_contours): answered `0.5`
- `relief-1` (aerial_ndsm_slope): answered `0.8`
- `relief-1` (fixed_all): answered `1`
- `relief-2` (aerial): answered `0.5`
- `relief-2` (aerial_contours): answered `1`
- `relief-2` (aerial_ndsm_slope): answered `1`
- `relief-2` (fixed_all): answered `1.25`
- `relief-3` (aerial): answered `0.5`
- `relief-3` (aerial_contours): answered `0.5`
- `relief-3` (aerial_ndsm_slope): answered `1`
- `relief-3` (fixed_all): answered `1.5`
- `relief-3` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `relief-4` (aerial): answered `0.5`
- `relief-4` (aerial_ndsm_slope): answered `1`
- `relief-6` (aerial): answered `0.5`
- `relief-6` (aerial_contours): answered `0.5`
- `relief-6` (aerial_ndsm_slope): answered `0.5`
- `relief-6` (fixed_all): answered `1`
- `relief-7` (aerial): answered `0.5`
- `relief-7` (aerial_contours): answered `0.5`
- `relief-7` (aerial_ndsm_slope): answered `0.6`
- `relief-8` (aerial): answered `0.6`
- `relief-8` (aerial_contours): answered `0.75`
- `relief-8` (aerial_ndsm_slope): answered `1`
- `relief-8` (fixed_all): answered `1`
- `relief-8` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `relief-9` (aerial): answered `0.5`
- `relief-9` (aerial_contours): answered `0.5`
- `relief-9` (aerial_ndsm_slope): answered `1`
- `relief-9` (fixed_all): answered `1.25`
- `relief-9` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `relief-10` (aerial): answered `0.6`
- `relief-10` (aerial_contours): answered `0.25`
- `relief-10` (fixed_all): answered `0.5`
- `steepest-1` (aerial_contours): answered `3`
- `steepest-1` (aerial_ndsm_slope): answered `3`
- `steepest-1` (fixed_all): answered `3`
- `steepest-2` (aerial): answered `2`
- `steepest-3` (aerial): answered `1`
- `steepest-6` (aerial): answered `1`
- `steepest-7` (aerial): answered `3`
- `steepest-8` (aerial_ndsm_slope): answered `1`
- `steepest-9` (aerial_contours): answered `1`
- `steepest-10` (aerial): answered `3`
- `steepest-10` (aerial_contours): answered `3`
- `tallest-1` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-3` (aerial_contours): answered `2`
- `tallest-3` (aerial_ndsm_slope): answered `2`
- `tallest-4` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-5` (aerial): answered `2`
- `tallest-5` (agent): answered `None`; The reply did not call submit_answer with an answer.
- `tallest-6` (aerial_contours): answered `1`
