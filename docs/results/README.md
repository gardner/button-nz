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
code 7136d87, #122; first run cfde155, #72, identical per section). Every
BDC parcel with a title whose point lies in one of Reefton's Residential
zones is screened on its own against Schedule 1A's siting rules:
the outline at least 2 m inside the boundary and 2 m from every LINZ building
outline. A section counts if at least one of the catalogue's 14 prefabs with
labelled dimensions fits. The LINZ outlines date from 2015–16, so a second
count also keeps 2 m from everything over 2 m on the 2020–24 LiDAR, trees
included: room without removing anything.

The parcels are then counted by **property**: a title, which is what's
bought, sold and regulated, and can cover several parcels (231 of
Reefton's titles cover 592 parcels between them). A property has room if
any of its parcels does.

| Count, with 0.6 m eaves | All 959 properties | 745 with a building (backyards) | All 1,320 parcels |
|---|---|---|---|
| Room under the LINZ outlines | 622 (65%) | 439 (59%) | 762 (58%) |
| Room clear of everything over 2 m on the LiDAR | 326 (34%) | 235 (32%) | 409 (31%) |

Without the eave allowance the property counts are 698 and 423 (parcels:
859 and 525). It's a screen, not a
verdict. It doesn't check:

- hazards (Reefton sits beside the Inangahua River);
- slope and floor level;
- the district plan and the NES-DMRU;
- services;
- lines between parcels on one title (each is screened as if a legal
  boundary, so a title of several parcels may have more room than this
  shows).

The report lists every limit.

## Many real sections: placement before and after (`button_nz.bench.batch`, #117)

The same 7 Reefton sections, from across the town screen's range of sizes,
each designed for one of the three example briefs, on the live app. Run
once on master `13b9d7b` ([before](batch/before/report.md)), and again on
master `6d24db2` ([after](batch/after/report.md)) with
`--repeat batch/before/results.jsonl`. Between the two, Muse was given the
title's road frontages and which is the address's street (#119), and the
room a plain rectangle fits in (#120). One section has no address and
wasn't designed.

| | Before | After |
|---|---|---|
| Designed / accepted | 6 / 6 | 6 / 6 |
| Accepted on the first attempt | 5 | 6 |
| Plain rectangles | 6 | 6 |
| AI visual passed its SAM check | 4 of 6 | 3 of 6 |

"As far from the street as the rules allow", walls to the address's
street's edge:

| Section | Before | After |
|---|---|---|
| 7 Smith Street | 2.34 m | 21.15 m |
| 81 Main Street | 3.67 m | 24.95 m |
| 2 Deemac Street | 38.63 m | 37.65 m |

**Notes:**
- Two of the three "far from the street" designs sat beside the street
  before the frontages and about 20 m from it after. The third was already
  far from it. With one design per brief and site, read this as an
  indication, not proof.
- **The baseline was cut short.** It picked 10 sections, and a redeploy
  restarted the API after 7. The after run repeated those 7 only.
- **The AI visual's verdicts were re-read from the API after each run.** The
  harness then read them before the visual was made, so it counted a missing
  one as a failure; it now waits. Across both runs the visual passed 7 of 12:
  its SAM check rejects a picture whose house was moved or reshaped.
