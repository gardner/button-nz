# Results

Every number here comes from a live run. The experiments call the Meta Model
API on the demo site, 35 Victory Street, Reefton; the town screen calls no
model and screens all of Reefton from open data. Each folder holds the run's
`report.md`, written by the benchmark from its own `results.jsonl` (one line
per question or design run), and that log. Each section names the commit
the run's code was at. Samples are small: read the differences as
indications, not proof.

## Experiment C: what does feedback buy? (`button_nz.bench.design_ablation`)

**On the surveyed site** ([report](experiment-c-surveyed-site/report.md),
code ff1f59a, #57). The two features the survey took for sheds are
existing buildings and the three trees are kept clear: the team's decisions
from the aerial photo and the LiDAR. The owner has since said nothing is
built on the section, so the sheds are a test of the separation check, not a
record of the site. Building separation and keep-clear are real checks here,
and can fail. Muse Spark 1.3, 3 briefs x 3 repeats.

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| one_shot | 9 | 5 (56%) | 100% | 0% | 1.0 | 0.0 | 74.2 | 0 |
| errors | 9 | 6 (67%) | 100% | 0% | 1.0 | 0.0 | 123.3 | 0 |
| evaluator | 9 | 9 (100%) | 100% | 100% | 1.6 | 0.0 | 110.8 | 0 |
| evaluator_lidar | 9 | 9 (100%) | 100% | 100% | 1.4 | 3.9 | 160.9 | 0 |

**On the plain site** ([report](experiment-c-plain-site/report.md), code
2f1eeec): no confirmed buildings or keep-clear areas, so building separation
is always "unknown" there. 3 briefs x 2 repeats.

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| one_shot | 6 | 4 (67%) | 83% | 0% | 1.0 | 0.0 | 44.3 | 0 |
| errors | 6 | 5 (83%) | 100% | 0% | 1.0 | 0.0 | 39.4 | 0 |
| evaluator | 6 | 6 (100%) | 89% | 100% | 1.5 | 0.0 | 58.0 | 0 |
| evaluator_lidar | 6 | 6 (100%) | 80% | 100% | 1.7 | 4.0 | 205.8 | 0 |

"Accepted" means no check failed on the final attempt; a check that can't be
decided (e.g. distance to an internal section line not confirmed as a legal
boundary) is "unknown", never a pass.

## Choosing the design model (#47)

The `evaluator_lidar` condition on the plain site, the same briefs and
repeats (code 984a978); Spark at default effort is the plain-site row above.

**Muse Wonder 1.0** ([report](model-muse-wonder/report.md))

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| evaluator_lidar | 6 | 6 (100%) | 100% | 100% | 1.8 | 4.0 | 306.7 | 0 |

**Muse Spark 1.3 at `reasoning_effort: max`** ([report](model-muse-spark-max/report.md))

| Condition | Runs | Accepted | Execution rate | Repair rate | Mean attempts | Mean observations | Mean s | Incomplete |
|---|---|---|---|---|---|---|---|---|
| evaluator_lidar | 6 | 5 (83%) | 70% | 67% | 1.7 | 4.0 | 446.5 | 0 |

Spark 1.3 at default effort stays the design agent: as often accepted, and
the fastest.

## Experiment A: does Muse understand LiDAR? (`button_nz.bench.lidar_qa`)

**Full run** ([report](experiment-a/report.md), code c007e76). 47 questions
about the site's terrain, each asked under five conditions: the aerial photo
alone, with contours, with nDSM and slope maps, with every fixed map, and
the agent, which chooses its own views and can query exact elevations.
Answers are computed from the LiDAR DEM and nDSM.

| Condition | n | Correct | Accuracy | No answer | Mean s |
|---|---|---|---|---|---|
| aerial | 47 | 23 | 49% | 0 | 23.8 |
| aerial_contours | 47 | 26 | 55% | 0 | 39.7 |
| aerial_ndsm_slope | 47 | 27 | 57% | 0 | 20.5 |
| fixed_all | 47 | 31 | 66% | 0 | 27.9 |
| agent | 47 | 39 | 83% | 7 | 14.9 |

By kind of question (correct / n):

| Condition | aspect | height_difference | relief | steepest | tallest |
|---|---|---|---|---|---|
| aerial | 9/10 | 2/10 | 1/10 | 5/10 | 6/7 |
| aerial_contours | 8/10 | 4/10 | 2/10 | 7/10 | 5/7 |
| aerial_ndsm_slope | 9/10 | 2/10 | 2/10 | 8/10 | 6/7 |
| fixed_all | 9/10 | 3/10 | 3/10 | 9/10 | 7/7 |
| agent | 8/10 | 10/10 | 7/10 | 10/10 | 4/7 |

The agent's gain is in what fixed maps can't give precisely: height
differences (10/10 against at most 4/10) and relief (7/10 against at most
3/10). It does worse on the tallest feature (4/7 against 7/7 with every map),
where three of its replies never called the answer tool. A reply that doesn't
call the tool gets one reminder (the API can't require it); 7 agent replies
still didn't, and count as wrong.

**First full run** ([report](experiment-a-first-run/report.md), code
2f1eeec): the agent scored 70% against 53–60% for the fixed views, with 14
replies that weren't tool calls scored wrong at once, which is what #60
fixed. It is kept for the record; the run above replaces it.

## Town screen: room for a real prefab in Reefton (`button_nz.bench.town_screen`)

**Reefton** ([report](town-screen/report.md), [map](town-screen/map.png),
code cfde155, #72; first run 98cdd48, identical per section). Every BDC title whose point lies in one of Reefton's
Residential zones is screened on its own against Schedule 1A's siting rules:
the outline at least 2 m inside the boundary and 2 m from every LINZ building
outline. A section counts if at least one of the catalogue's 14 prefabs with
labelled dimensions fits. The LINZ outlines date from 2015–16, so a second
count also keeps 2 m from everything over 2 m on the 2020–24 LiDAR, trees
included: room without removing anything.

| Count, with 0.6 m eaves | All 1,320 sections | 986 with a building (backyards) |
|---|---|---|
| Room under the LINZ outlines | 762 (58%) | 488 (49%) |
| Room clear of everything over 2 m on the LiDAR | 409 (31%) | 258 (26%) |

Without the eave allowance the counts are 859 and 525. It's a screen, not a
verdict. It doesn't check:

- hazards (Reefton sits beside the Inangahua River);
- slope and floor level;
- the district plan and the NES-DMRU;
- services;
- lines between parcels on one title.

The report lists every limit.

## AI visual: how often it passes its silhouette check (`button_nz.bench.visual_check`, #133)

After a design is accepted, Muse Image turns its render into a photo-like
picture, and it is shown only if SAM 3.1 finds the house in it overlapping
the design's silhouette with an IoU of at least 0.60. On the 12 accepted
designs of the batch runs (#117), the visual was re-made as the app makes
it (code 6c5c1aa):

| Design | Batch run (one edit) | Re-run, one edit (IoU) | Up to two edits (edits, IoU) |
|---|---|---|---|
| 4ee3c533 | passed | passed (0.82) | failed (2, 0.36) |
| 14e33e79 | failed | failed (0.36) | failed (2, 0.13) |
| 2814a497 | failed | passed (0.78) | passed (2, 0.76) |
| 7b219d6b | passed | passed (0.72) | passed (1, 0.71) |
| 02003a9b | passed | passed (0.83) | passed (1, 0.91) |
| 3ca9262c | passed | passed (0.71) | passed (1, 0.73) |
| 1f3ae911 | failed | failed (0.42) | failed (2, 0.49) |
| b6d7a54d | failed | passed (0.74) | failed (2, 0.21) |
| fb1d8b45 | passed | failed (0.59) | passed (2, 0.70) |
| c5832e90 | failed | failed (0.42) | failed (2, 0.48) |
| 910c6d05 | passed | passed (0.79) | passed (1, 0.81) |
| 1b52b41d | passed | passed (0.83) | passed (1, 0.61) |
| **Passed** | **7 of 12** | **8 of 12** | **7 of 12** |

- **A second edit helps a little, not as much as hoped.** In the two-edit
  run the first edit passed 5 of 12 and the second rescued 2 of the 7 it
  made. If edits were independent coin flips at the one-edit rate, two
  would pass about 9 in 10; they aren't. Three designs failed every time
  (14e33e79, 1f3ae911, c5832e90): failure sticks to the design.
- **SAM finds the right building.** In every failure the best-matching mask
  is the new dwelling: Muse Image drew it bigger (14e33e79: 1.3x and once
  13x its area; c5832e90: 2.3x) or a little off where it is (IoU 0.2–0.5
  at about the right size). The smallest dwelling in frame (14e33e79, 0.3%
  of the picture) fails most.
- **A prompt describing today's render did worse.** The prompt still calls
  the dwelling "plain light-coloured" and the sky "the black area", from an
  older render. A prompt describing the textured dwelling and the sky, and
  saying nothing may extend outside its box, passed 6 of 12 to the
  current prompt's 8, so the prompt is unchanged.
- **Not done:** lowering the 0.60 threshold or showing a rejected picture.
  The check exists so the picture can't misrepresent the checked design.

Each run is one sample per design, and the one-edit rate varied from 5 to
8 of 12 between runs, so differences of one or two designs are noise.
