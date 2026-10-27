# Button NZ — Meta Global AI Developer Hackathon Plan

**Version:** 1.0  
**Date:** 28 October 2026  
**Submission deadline:** 4 November 2026, 9:00 PM US Eastern Time (5 November, 3:00 PM NZDT)  
**Primary theme:** Push the Frontier  
**Secondary theme:** Build for Your World  
**Competition track:** Indie

---

## 1. Executive summary

### The vision

**Button NZ — Unlock the housing hiding in your backyard.**

Button NZ helps property owners discover opportunities to add housing to their land. By combining Meta's AI models, aerial imagery, LiDAR, planning regulations, real prefab housing products and Blender, the system transforms a property address into interactive, evidence-backed 3D housing concepts.

The longer-term product will guide property owners from initial feasibility exploration through housing product selection, professional engagement, procurement and construction.

For the Meta Global AI Developer Hackathon, we will demonstrate a focused but technically ambitious part of this vision.

### The core innovation

Build an **autonomous spatial-design agent capable of understanding, reconstructing, modifying and evaluating real physical environments**.

The agent will:

1. Examine a real property using aerial photographs, geographic information and LiDAR measurements.
2. Use Meta's SAM models to identify physical objects and environmental features.
3. Generate different visual representations of elevation data to investigate the property's three-dimensional characteristics.
4. Write and execute Blender Python scripts to construct a 3D scene.
5. Position real prefab housing models on the property.
6. Inspect rendered results and independently calculated spatial constraints.
7. Automatically revise designs when errors or conflicts are detected.
8. Generate alternatives and explain their relative merits.
9. Match proposed housing concepts with available prefabricated products and the next required professional services.

The central demonstration will show an AI agent **reasoning about the physical world and controlling real 3D engineering software**, rather than generating an attractive but unverified image.

### Important technical decisions

- **No reinforcement learning.** We will use inference-time agentic reasoning, tool execution, verification and optional supervised fine-tuning.
- Muse will write real Blender Python code through the `bpy` API.
- Blender will run headlessly in isolated environments, with remote GPUs used for rendering.
- LiDAR and GIS will provide measured geometric evidence.
- Generative models will provide interpretation, scene construction, design alternatives and visual enhancement.
- Geometry and planning checks will be independent of the AI model.
- Fine-tuning must never become a dependency of the core demonstration.

---

## 2. Hackathon strategy

### Judging priorities

| Criterion | Weight | Button NZ strategy |
|---|---:|---|
| Real-world impact | 30% | Address the supply-side housing problem by helping homeowners investigate additional dwellings |
| Creative use of Meta tooling | 25% | Muse-controlled Blender, active LiDAR perception, SAM segmentation, optional Meta-model fine-tuning |
| Demonstration | 25% | Dramatic aerial-to-3D transformation and visible autonomous design correction |
| Technical execution | 20% | Verified geometry, reproducible agent actions, quantitative evaluations and resilient rendering |

The biggest opportunity is to demonstrate an **unexpected capability of Meta's models**, not simply to use as many models as possible.

The technical narrative should be:

> We gave Meta's models the ability to inspect real terrain, choose how to visualise unfamiliar geospatial data, program Blender, test their own designs against physical constraints, and improve those designs autonomously.

### Commercial and social impact

New Zealand is a useful initial market because it has relatively accessible national geospatial datasets and recent reforms for small standalone dwellings.

Qualifying new detached dwellings up to 70 m² can use the 2026 building-consent exemption, subject to statutory conditions, licensed professional involvement and a PIM. A separate national environmental standard provides a possible resource-consent-free pathway for qualifying detached minor residential units.

Button NZ will help users understand which pathways might apply, what information remains unknown and which professionals they should approach.

**We will not claim that an automatically generated design is consented, buildable or fully compliant.**

The hackathon demonstrates earlier, lower-cost decision support—not replacement of qualified designers, surveyors, engineers or councils.

---

## 3. The target demonstration

### User scenario

A homeowner enters a New Zealand property address and asks:

> "I want to add a two-bedroom prefab house. Keep as much of my existing garden as possible, avoid unnecessary earthworks, and show me what the options would cost."

### Demonstration journey

**Step 1 — Identify the property**

The system displays:

- Aerial imagery.
- Parcel geometry.
- Existing building outlines.
- Measured terrain.
- Known site features and important data limitations.

The owner confirms the site and any important existing structures.

**Step 2 — Reconstruct the property**

Muse examines the aerial image and LiDAR-derived visualisations.

SAM identifies buildings, trees and other relevant objects. GIS provides terrain and coordinate information.

Muse then writes Blender Python code to reconstruct an approximate 3D representation of the existing site.

The frontend displays the reconstructed property as an interactive 3D model.

**Step 3 — Discover housing opportunities**

Muse receives the user's brief and a small catalogue of real prefab homes.

It explores different building footprints, locations and orientations, including constraints such as:

- Parcel boundaries.
- Existing building footprints.
- Applicable known setbacks.
- Terrain elevation and slope.
- Preserved gardens and trees.
- Access and servicing uncertainties.
- Product dimensions and budget preferences.

**Step 4 — Demonstrate autonomous correction**

The agent proposes a placement that fails a supported geometric or planning check.

The system returns the exact failure and its supporting measurements.

Muse examines the feedback, requests an additional LiDAR view if useful, and modifies the Blender scene to produce another candidate.

This is the key demonstration of technical intelligence.

**Step 5 — Compare concepts**

The system presents two or three materially different concepts, such as:

- A compact dwelling that preserves the most garden space.
- A larger dwelling with a different orientation.
- A proposal that may require further investigation into earthworks or access.

Each proposal has a revision identifier, render, interactive geometry, known constraints and outstanding questions.

**Step 6 — Connect the proposal to reality**

For the preferred design, Button NZ displays:

- The corresponding real prefab product.
- Published price and specifications where available.
- Site preparation and installation requirements.
- Known cost exclusions and unpriced work.
- Potential approval pathways and checks still required.
- Appropriate next professionals or suppliers to contact.

**Step 7 — Natural-language revision**

The user asks:

> "Move the house farther from the existing dwelling and make the deck face north."

Muse updates the Blender model, reruns the available spatial checks and generates a revised result.

The user can compare the revision with the original.

### Definition of a successful demo

A genuine end-to-end run must produce a 3D housing concept from a confirmed property, use Muse-authored Blender code, perform independent spatial checks, and successfully execute at least one AI-directed revision.

The demo may use cached base property data and precomputed high-resolution renders. The agent-driven revision must be real and reproducible.

---

## 4. Scope and priorities

### P0 — Essential hackathon deliverable

These capabilities must work even if every experimental feature fails.

- One real, suitable New Zealand demonstration property.
- Aerial photograph, parcel boundary, DEM/DSM and existing-building context.
- A metric, georeferenced terrain mesh.
- Muse generating and executing Blender `bpy` scripts.
- Importing at least one real prefab model with verified manufacturer dimensions.
- An independent geometry and narrow planning-constraint evaluator.
- A working feedback-and-revision loop.
- Interactive GLB output and at least one architectural render.
- A sourced prefab product and an explanation of outstanding costs and requirements.
- A coherent recorded demonstration and repeatable live workflow.

### P1 — High-value differentiators

Implement once the complete P0 journey works.

- SAM 3.1 aerial object segmentation.
- Muse selecting LiDAR visualisations to resolve uncertainties.
- Multiple proposed housing configurations.
- Multi-view scene reconstruction verification.
- A second independently assessed test property.
- Comparative evaluation against a simpler one-shot agent.
- Background Cycles rendering and polished visual presentation.

### P2 — Optional research features

Timebox these experiments and remove them from the submission path if they do not show early promise.

- SAM 3D Objects reconstruction.
- Muse Glimmer supervised fine-tuning.
- Daily human-in-the-loop training.
- DINOv3 satellite-feature experiments.
- Synthetic LiDAR camera flyovers for multimodal reasoning.
- Muse Image architectural compositing.
- Voice-directed design edits.
- Automated Meta-assisted demo video production.

### Explicitly out of scope

- Reinforcement learning.
- A complete national planning-rule engine.
- Automatic consent applications or approvals.
- Accurate construction-ready architectural drawings.
- Real procurement and financial transactions.
- Supplier quotation automation.
- Multi-council production coverage.
- Full photogrammetric reconstruction of every site object.
- Production mobile applications.

These are potential future Button NZ capabilities, not prerequisites for the hackathon.

---

## 5. System architecture

### Overall pipeline

**Property discovery**

Address → parcel confirmation → aerial imagery → LINZ building outlines → DEM/DSM → source metadata.

**Site perception**

Muse vision reasoning → SAM 3.1 segmentation → object classification and geospatial alignment → human confirmation where needed.

**Spatial understanding**

Terrain and surface-height analysis → LiDAR visualisation tools → numeric elevation queries → structured site interpretation.

**Design**

User housing brief + prefab catalogue → Muse design agent → Blender Python scripts → scene construction.

**Verification**

Independent geometric checks → planning-rule checks where supported → source-linked feedback → Muse revises the design.

**Presentation**

GLB export → interactive browser scene → asynchronous GPU rendering → project revisions and comparison.

**Commercial handoff**

Matched prefab product → known specifications → cost breakdown → unresolved site investigations → supplier or contractor enquiry concept.

### Proposed implementation stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, React Three Fiber |
| Map | MapLibre |
| API | New Next.js/Python services built in this repository |
| Geometry | Shapely, GeoPandas, Rasterio, PyProj |
| Geospatial persistence | Postgres/PostGIS |
| Agent | Muse Wonder or Muse Spark through Meta Model API |
| Segmentation | SAM 3.1 |
| 3D modelling | Blender Python API |
| Interactive output | glTF/GLB |
| Rendering | Blender Cycles/OptiX |
| GPU execution | Local RTX GPU only (Modal is a stretch goal) |
| Artifact storage | S3-compatible storage to be provisioned |
| Job tracking | Simple job tracking built in this repository |
| Training | Axolotl, PEFT, Muse Glimmer |
| Evaluation | Pytest, deterministic geometry checks and recorded agent traces |
| Development | Muse Code alongside the team's normal coding tools |

Use `pnpm` for the Node application and `uv` for the Python components.

There is no existing Button NZ platform. This is a greenfield build in this repository. For the hackathon, make the scene pipeline independently runnable without depending on larger product work orchestration.

---

## 6. Geospatial reconstruction

### 6.1 Acquire the property data

Start with 35 Victory Street, Reefton. Confirm adequate source data is available. Record owner permission to publish imagery and renders before any public release.

Required inputs:

- Legal parcel reference geometry.
- Georeferenced aerial imagery.
- LINZ building outlines.
- West Coast LiDAR 1 m DEM.
- West Coast LiDAR 1 m DSM.
- Available planning-zone context.
- Manufacturer-defined prefab footprints.

Optional input:

- Raw classified LiDAR point clouds.
- Oblique site photographs.
- Owner-supplied measurements.
- Explicitly confirmed existing structures and vegetation.

Use NZTM2000 (EPSG:2193) for horizontal site coordinates and the published vertical datum for elevations. Transform all source layers into a consistent local metre-based coordinate system for Blender.

Retain imagery acquisition dates, LiDAR capture dates, source licensing and uncertainty information.

### 6.2 Build the terrain

Generate a Blender terrain mesh from the DEM.

Each DEM cell contributes an elevation sample. The terrain mesh is expressed relative to a local origin, avoiding large geospatial coordinates inside Blender.

The DSM provides information about above-ground features.

Calculate a normalised surface-height representation:

`nDSM = DSM - DEM`

Align the rasters and handle nodata before calculating differences.

Do not treat nDSM as exact building-wall or vegetation height. It represents measured surface differences subject to sampling, registration and temporal limitations.

### 6.3 Construct existing features

Use authoritative or measured geometry when available.

- Buildings: georeferenced roof footprints and supported height estimates.
- Trees: detected crown locations, approximate heights and procedural tree assets.
- Gardens: aerial segmentation polygons projected onto terrain.
- Driveways: surface polygons with aerial texture.
- Sheds: existing outlines or confirmed geometry.
- Fences and other small features: user-confirmed, approximate or unknown.

Each object should have provenance and confidence metadata.

### 6.4 SAM 3.1 perception

Have Muse inspect the source aerial photograph and formulate targeted segmentation requests.

Example concepts:

- Residential building roofs.
- Sheds.
- Individual trees or tree canopies.
- Garden beds.
- Driveways and paved areas.

Process each returned mask into polygons in the source image coordinate system, then georeference it using the image transform.

Compare detections with existing GIS evidence.

Where sources disagree, preserve both and request confirmation rather than silently choosing one.

### 6.5 Optional SAM 3D Objects

SAM 3D Objects accepts an image and an object mask and attempts to reconstruct the object's geometry, pose and appearance.

Evaluate it on selected sheds or distinctive objects, particularly when oblique photography is available.

Do not use reconstructed geometry for legal setback or foundation calculations.

Compare whether the additional reconstruction improves visual quality enough to justify its latency and integration complexity.

---

## 7. Novel LiDAR representations

One of our strongest technical research opportunities is translating geospatial data into visual forms that Muse may understand particularly well.

We will build a small **LiDAR Visualisation Toolkit**.

### Supported representations

| Representation | What it communicates | Intended use |
|---|---|---|
| Aerial RGB | Appearance and visible features | General site understanding |
| DEM hillshade | Terrain shape | Ridges, banks, depressions |
| Elevation contours | Relative elevation | Site layout and grading |
| Slope heatmap | Terrain steepness | Placement and earthwork screening |
| nDSM heatmap | Above-ground surface heights | Structures and vegetation |
| RGB composite | Height, slope and above-ground height | Multimodal experimentation |
| Surface-normal map | Ground orientation | Slope direction |
| Elevation cross-section | Exact sampled terrain profile | Foundations and layout decisions |
| Classified point-cloud projection | Heights and object classes | Spatial context |
| Synthetic flyover | Multiple perspectives on one 3D scene | Video-based model reasoning |

These are alternative representations of existing measurements. They do not create missing physical information.

### Active-perception agent

Rather than always send every visualisation, allow Muse to request the representation it needs.

Proposed tools:

- `get_site_context()`
- `get_aerial_view()`
- `render_hillshade(azimuth, altitude)`
- `render_contours(interval_m)`
- `render_height_map(mode)`
- `render_cross_section(start, end)`
- `inspect_elevation(polygon)`
- `get_building_footprints()`
- `get_object_masks(category)`
- `render_site_view(camera)`
- `compare_scene_to_evidence(scene_revision)`

Each tool returns actual imagery or calculated measurements and source metadata.

The model should be allowed to request additional observations when its current understanding is uncertain.

### Research hypothesis

**A model that can select and examine spatial representations of its own choosing will make better physical design decisions than the same model receiving only aerial RGB imagery.**

This is not an assumed result. It must be evaluated.

---

## 8. Muse-controlled Blender design agent

### 8.1 Agent responsibilities

Muse will directly author and revise Python scripts using Blender's `bpy` API.

It can:

- Construct site geometry.
- Import building models.
- Place, rotate and modify scene objects.
- Apply materials.
- Configure cameras.
- Configure lighting.
- Render scene previews.
- Export GLB and .blend artifacts.
- Revise scenes based on tool and visual feedback.

The model is not limited to a predefined sequence of `move_house` operations.

However, it must use approved scene contracts and run within an isolated execution environment.

### 8.2 Scene contract

Every design operation will reference a pinned scene context containing:

- Property ID and data revision.
- Parcel geometry and coordinates.
- Terrain surface.
- Existing fixed features.
- User-confirmed preserve/remove constraints.
- Prefab product identifiers and true dimensions.
- Relevant checked planning constraints.
- Unknown and conditional requirements.
- Current design revision.

The canonical planning record should be stored separately from Blender's `.blend` file.

Blender is the design and visualisation engine, not the authoritative source of regulatory truth.

### 8.3 Design loop

1. Muse reads the site context and housing brief.
2. Muse selects a prefab and proposes a placement.
3. Muse writes or modifies a Blender Python script.
4. The isolated Blender worker executes the script.
5. The system exports a preview and scene measurements.
6. The independent evaluator checks geometry and known constraints.
7. Muse receives errors, numerical feedback and visual previews.
8. Muse revises the script where useful.
9. The final checked candidate is saved as a versioned concept.

Limit agent iterations and compute budgets, with a default maximum of approximately three revision attempts during the demo.

Failed attempts should remain inspectable. An unsuccessful attempt should not silently become a passing design.

### 8.4 Validation

Implement deterministic checks for:

- Footprint location within the supported parcel region.
- Collision with confirmed existing structures.
- Setback measurements for explicitly supported rules.
- Product dimensions.
- User-defined preservation areas.
- Terrain elevations under the footprint.
- Basic scene object alignment.
- Whether render geometry corresponds to the stored proposal.

Unverified requirements remain unknown.

This evaluator can supply corrections to Muse but must not let Muse override an objective failed check through narrative reasoning alone.

### 8.5 Rendering strategy

Use two rendering paths.

**Interactive and preview path**

- Lower-resolution Blender preview renders.
- Modest sample counts.
- GLB export for browser-based exploration.
- Frequent progress updates.

**Presentation path**

- Blender Cycles.
- OptiX acceleration on compatible NVIDIA GPUs.
- High-resolution architectural images.
- Multiple camera angles.
- Background rendering and artifact delivery.

Rendering may take several minutes. The user can explore completed geometry while final images are being produced.

The product is not required to finish rendering within the duration of its recorded demonstration.

### 8.6 GPU execution

Run Blender on the local NVIDIA GPU. Modal is a stretch goal only if time allows.

Build a pinned Blender container containing the required Python scripts, models and rendering dependencies.

Keep expensive GPU allocation bounded and cache static site assets.

The orchestration service should submit a job, store its state and retrieve artifacts when complete.

Do not add a cloud rendering path until the local pipeline works end to end.

Scripts generated by an LLM must run with restricted filesystem access, no unnecessary network permissions, timeouts, limited resources and no production credentials.

---

## 9. Planning and prefab catalogue

### Regulatory scope

Implement a narrow initial rule set applicable to the chosen demonstration property.

Focus on the 2026 small standalone dwelling and detached minor residential unit pathways where relevant.

Keep building-consent exemptions and resource-consent exemptions separate.

The UI must distinguish:

- A constraint checked using available evidence.
- A constraint that fails.
- A conditional pathway.
- An unresolved or unavailable requirement.

Include relevant council information, hazards, services and access limitations only where supported by sourced data.

### Prefab marketplace prototype

Build a curated catalogue of three to five real prefab products.

For each product, store:

- Supplier name and product identifier.
- Actual dimensions and footprint.
- Floor area and bedroom count.
- Build type: transportable, modular or SIP kit.
- Base published price, source date and tax basis.
- Inclusions and exclusions.
- Claimed delivery regions.
- Assembly or installation service availability.
- Source URL and contact method.

Do not infer local installation availability from nationwide product delivery.

For each proposed housing concept, match product geometry to the supported layout and generate a transparent preliminary cost plan.

Show unpriced costs for foundations, transport, cranage, services, professional work and other material unknowns.

The hackathon will demonstrate catalogue matching and an enquiry-ready handoff—not a functioning transactional marketplace.

---

## 10. Fine-tuning experiment

### Objective

Determine whether task-specific SFT improves Meta-model performance on unusual aerial/LiDAR representations and structured 3D scene planning.

**Fine-tuning is optional and will not block the main demonstration.**

### Candidate model

Use open-weight Muse Glimmer 30B with the official supervised fine-tuning recipes.

Begin with QLoRA through Axolotl, using the published Meta recipe and pinned dependencies.

The official reference configuration is verified on H100 hardware; local RTX 5090 training is an experiment, not a guaranteed supported configuration.

### Training objective

Given an aerial photograph, one or more LiDAR representations and a specific question, output a structured interpretation or proposed geometric action.

Potential tasks:

- Identify the most appropriate terrain region for investigation.
- Distinguish elevated vegetation from building roofs.
- Recognise when slope evidence changes a placement decision.
- Request a more useful LiDAR representation.
- Produce a structured scene plan.
- Repair an invalid placement using explicit feedback.

Avoid training the model to produce arbitrary entire Blender programs initially.

### Dataset creation

Generate synthetic residential sites using Blender and GIS utilities.

Vary:

- Parcel shape and orientation.
- Terrain slope and relief.
- Building placement.
- Roof geometry.
- Vegetation.
- Garden areas.
- Prefab footprints.
- Existing obstacles.

Export aerial images, DEM-like rasters, DSM-like rasters, contours, masks and labelled scene parameters.

Initial target:

- 500–1,500 synthetic supervised examples.
- Approximately 50–100 human-reviewed examples if feasible.
- Several genuinely held-out properties for evaluation.

Treat these as workload targets, not validated sample-size requirements.

Split evaluation data by property or underlying scene family, never by individual camera view.

### Human-in-the-loop workflow

Have baseline Muse and SAM generate candidate annotations.

Reviewers inspect the imagery, LiDAR information and proposed labels.

Corrections are saved as structured training examples.

Prioritise:

- Incorrect object identification.
- Incorrect elevation interpretation.
- Confusion between roofs, ground and vegetation.
- Failure to recognise uncertainty.
- Invalid placement proposals.
- Correctable Blender scene errors.

### Daily MLOps pipeline

1. Collect approved new examples and difficult failures.
2. Validate the dataset and record its version.
3. Launch a bounded QLoRA training run.
4. Evaluate the candidate against base Glimmer and the current best adapter.
5. Deploy only if the candidate passes quality and reliability gates.
6. Record difficult remaining failures for the next annotation round.

Every checkpoint must retain the dataset, model, configuration and evaluation version.

Use a fixed base checkpoint for comparable experiments, rather than repeatedly training on yesterday's model without controls.

### Deployment rule

The main application should use the hosted Muse agent by default.

A fine-tuned Glimmer specialist can provide site interpretations if it outperforms the base model on held-out cases.

If SFT does not produce a meaningful improvement, retain the untuned model and report the experiment accurately.

**No RL, GRPO or reward-training pipeline is planned.**

---

## 11. Evaluation strategy

We need quantitative evidence that the unusual Meta AI integration improves actual results.

### Experiment A — Understanding LiDAR

Compare the same base model using:

1. Aerial RGB imagery alone.
2. Aerial RGB plus contours.
3. Aerial RGB plus nDSM and slope maps.
4. Multiple fixed geospatial visualisations.
5. Agent-selected visualisations and elevation queries.
6. Fine-tuned Glimmer, if successfully trained.

Use independently calculated answers for slope direction, relative heights, footprint relationships and other objective spatial questions.

### Experiment B — Scene reconstruction

Compare:

- GIS-only procedural reconstruction.
- GIS plus SAM segmentation.
- GIS plus SAM 3D reconstruction where applicable.
- Muse-refined Blender scene.

Metrics:

- Building footprint overlap.
- Height error against trusted measurements.
- Object placement error.
- Render-to-mask alignment.
- Human correction effort.
- Time and compute cost.

### Experiment C — Autonomous Blender design

Compare:

- One-shot Muse-generated Blender scene.
- Muse with execution-error feedback.
- Muse with visual inspection and independent constraint feedback.
- Muse with active LiDAR tool selection.

Metrics:

- Successful Blender execution rate.
- Proportion passing supported geometric checks.
- Repair success rate.
- Unsupported or invented findings.
- Number of agent iterations.
- End-to-end latency.
- Cost per usable design.

### Experiment D — User usefulness

Have at least one knowledgeable property or construction practitioner assess concepts.

Ask whether the output provides a clearer understanding of available opportunities, material concerns and useful next actions.

Capture criticism and corrections rather than treating informal feedback as certification.

### Reporting requirements

Report actual measured values, sample sizes, evaluation methods and failure cases.

Do not present hypothetical benchmark improvements as results.

A small honest benchmark demonstrating one surprising capability will be more persuasive than an unsupported claim of general spatial intelligence.

---

## 12. Using Meta tools during development

### Muse Code

Use Muse Code where available for:

- Blender worker implementation.
- Geospatial processing utilities.
- SAM integration.
- React Three Fiber UI.
- Evaluation harnesses.
- Tests and bug fixes.
- CI workflows.
- Production of supporting technical documentation.

Parallelise independent tasks where practical and supported by the installed Muse Code version.

Record examples of actual AI-assisted development, particularly instances where Muse discovers, tests and corrects its own code.

### Muse Image

Potential uses:

- Demo title graphics.
- Product storyboards.
- Architectural art direction.
- Visual finish and material exploration.
- Supporting presentation illustrations.

AI-generated aesthetic imagery must be identified as illustrative and not substituted for measured site geometry.

### Muse-assisted video production

Use Muse to:

- Analyse recorded screen captures.
- Identify strong demonstration moments.
- Produce an edit decision list.
- Write FFmpeg or Blender editing scripts.
- Generate captions and explanatory overlays.
- Help assemble a concise technical video.

Using Meta models during production may improve the demo, but the organisers have not explicitly confirmed that this receives additional Meta-tooling points.

### Partner infrastructure

Modal is a stretch goal for GPU execution. The hackathon build runs on the local GPU only.

Baseten and Fireworks are possible inference providers, but will only be integrated if they solve an actual problem.

Partner usage is not an automatic source of extra judging points.

---

## 13. Demo video production

### Target length

Aim for approximately 2–3 minutes, subject to the authenticated submission requirements.

The publicly available rules reviewed do not establish a mandatory three-minute limit for the running application or conclusively establish the video-duration requirement.

Long Blender renders can be shown as clearly labelled accelerated footage.

### Proposed storyboard

| Timing | Sequence |
|---|---|
| 0:00–0:15 | The housing problem and the Button NZ promise |
| 0:15–0:35 | Enter property address; show aerial imagery and LiDAR |
| 0:35–0:55 | SAM identifies features; aerial image transforms into an approximate 3D site |
| 0:55–1:25 | Muse writes and executes Blender Python; prefab appears |
| 1:25–1:50 | Placement fails a check; Muse requests another observation and repairs it |
| 1:50–2:15 | Compare finished housing concepts and interactive 3D results |
| 2:15–2:35 | Show real prefab catalogue match, cost uncertainties and next steps |
| 2:35–3:00 | Evaluation results, technical innovation and social-impact vision |

### Required production assets

- Original aerial photograph.
- LiDAR visualisation montage.
- SAM segmentation overlay.
- Muse agent tool trace.
- Blender Python execution.
- Initial unsuccessful placement.
- Evidence-backed corrective action.
- Interactive 3D walkthrough.
- High-quality render.
- Real prefab matching interface.
- Benchmark comparison.
- Concise closing statement.

The final recording must accurately distinguish live system behaviour, cached results, accelerated rendering and illustrative imagery.

---

## 14. Day-by-day delivery

### Wednesday 28 October — Lock scope and establish baseline

**Objectives**

- Confirm submission requirements, track and account access.
- Claim Meta and eligible partner credits.
- Select and verify the demonstration property.
- Acquire the aerial and LiDAR data.
- Freeze the core demo story.
- Establish baseline model calls and a runnable Blender worker.

**Exit criterion:** A known property can be loaded into a reproducible 3D scene, with at least one successful Muse API tool interaction.

### Thursday 29 October — Build geospatial scene reconstruction

**Objectives**

- Align parcel, aerial and LiDAR layers.
- Generate the DEM terrain mesh.
- Create approximate existing structures.
- Import at least one real prefab asset.
- Export and view the scene as GLB.
- Establish GPU rendering and artifact storage.

**Exit criterion:** A real property appears in a browsable, correctly scaled 3D scene with a prefab asset.

### Friday 30 October — Implement the Muse-to-Blender loop

**Objectives**

- Give Muse access to scene context and approved tools.
- Generate executable `bpy` scripts.
- Return Blender errors and scene measurements.
- Implement core geometry checks.
- Allow the agent to repair invalid designs.
- Record an initial end-to-end trace.

**Exit criterion:** Muse produces a scene, detects a reported placement failure and successfully executes a corrective revision.

### Saturday 31 October — Complete the main demo

**Objectives**

- Connect the UI, Muse agent, Blender worker and evaluator.
- Add interactive scene viewing.
- Support a natural-language revision.
- Integrate a minimal prefab product and cost summary.
- Record the first complete demo.

**Hard milestone:** The core end-to-end demonstration must work by the end of 31 October.

If it does not, immediately defer SAM 3D, fine-tuning and advanced video effects.

### Sunday 1 November — Add Meta multimodal differentiation

**Objectives**

- Integrate SAM 3.1 masks.
- Produce contour, hillshade and cross-section tools.
- Enable Muse to request additional LiDAR observations.
- Compare this behaviour with aerial-only reasoning.
- Implement two or three housing concept alternatives.

**Exit criterion:** At least one meaningful agent-selected spatial observation affects or explains a design decision.

### Monday 2 November — Evaluate and experiment

**Objectives**

- Run the core benchmark suite.
- Test another site or held-out cases.
- Validate geometry and source provenance.
- Attempt Glimmer QLoRA only if the training pipeline is ready.
- Test SAM 3D on a selected object if time permits.
- Capture measurable results and known limitations.

**Exit criterion:** A stable primary demo plus a reproducible technical evaluation.

### Tuesday 3 November — Refine the user experience

**Objectives**

- Improve visual quality and scene presentation.
- Polish the three housing alternatives.
- Improve planning explanations and source links.
- Add clearer cost exclusions.
- Review results with a knowledgeable practitioner.
- Produce an initial video edit.

**Exit criterion:** A judge can understand the project, its novelty and its limitations without a technical walkthrough.

### Wednesday 4 November — Finalise and submit

**Objectives**

- Freeze all critical dependencies.
- Run a clean-room deployment test.
- Record the definitive demonstration.
- Finish the video, README and evaluation report.
- Verify all shared links and access permissions.
- Prepare the submission and submit early.

Allow the New Zealand morning of 5 November only as a contingency, rather than planning to submit near the 3 PM NZDT deadline.

---

## 15. Deliverables

### Required submission artifacts

1. **Working application:** A deployed Button NZ demonstration supporting the chosen property and housing-design journey.
2. **Demo video:** A concise end-to-end story centred on autonomous Muse-to-Blender design and correction.
3. **Source repository:** The runnable application, Blender worker, geometry evaluator and deployment instructions, with clear rights to submitted code.
4. **Technical README:** Architecture, Meta tooling, data sources, limitations and reproducibility instructions.
5. **Evaluation report:** Baselines, test cases, measurements and representative failures.
6. **Sample project artifacts:** Georeferenced scene metadata, `.blend`, GLB, final PNG renders and recorded agent tool traces.
7. **Product story:** User problem, social impact, commercial opportunity and future development path.

### Optional research artifacts

- SAM 3D reconstruction comparison.
- LiDAR-representation benchmark.
- Synthetic spatial dataset.
- Muse Glimmer fine-tuned adapter.
- HITL labelling interface.
- Training run history and model evaluation dashboard.

---

## 16. Main risks and fallback plans

| Risk | Mitigation |
|---|---|
| Muse-generated Python fails | Keep a known-good scene template, bounded repair loop and deterministic fallback |
| Incorrect regulatory interpretation | Limit rules to sourced, tested checks and explicitly flag missing verification |
| LiDAR and imagery don't align | Validate CRS, datum, footprint registration and capture dates |
| SAM misses objects in aerial imagery | Fall back to building outlines and owner-confirmed features |
| SAM 3D performs poorly on overhead photographs | Keep measured/procedural geometry and omit SAM 3D |
| GPU rendering is slow | Return GLB and previews first; render final images asynchronously |
| Fine-tuning underperforms | Retain hosted/base Muse and publish the negative result if useful |
| Cloud credits run out | Set spend limits; use local GPU or reduced-quality rendering |
| Marketplace data is incomplete | Display sourced products and explicit supplier/service unknowns |
| Agent outputs look good but contain geometric errors | Require independent checks and separate visual aesthetics from spatial validity |
| Demo environment fails | Maintain a verified recorded workflow and pinned, reproducible artifacts |
| Work expands beyond deadline | Enforce the 31 October end-to-end milestone and cut P2 experiments |

---

## 17. Winning demonstration criteria

The entry should be able to answer **yes** to each question:

- Did Meta AI meaningfully control real 3D software?
- Did the AI reason about an actual property using more than a text prompt?
- Did LiDAR or segmentation contribute genuinely useful information?
- Could the model request observations or tools to improve its understanding?
- Did the agent detect and correct at least one real design problem?
- Was the corrected design independently validated for the constraints actually implemented?
- Did the application produce a useful housing concept tied to a real product?
- Can a judge reproduce the core behaviour?
- Can we show credible measurements rather than invented performance claims?
- Is the potential social and commercial impact obvious?

The project should not depend on having invented a new foundation model.

Its novelty should come from **giving existing Meta models a new capability through an intelligently designed environment, spatial tools and feedback mechanisms**.

---

## 18. Post-hackathon product roadmap

This competition entry should become a genuine part of Button NZ rather than a throwaway prototype.

### Phase 1 — Consumer housing feasibility

Expand supported properties, verified geospatial sources, planning rules, concept editing, comparison and cost transparency.

### Phase 2 — Supplier and contractor marketplace

Introduce supplier onboarding, verified product catalogues, service coverage, delivery suitability, builder matching and quote enquiries.

### Phase 3 — Professional workflows

Provide designer, engineer, surveyor and council handoff packages containing evidence, selected concept revisions, unresolved questions and supporting documentation.

### Phase 4 — Scalable housing opportunity discovery

Support more councils and development typologies, identify possible additional-housing opportunities at scale, and improve the accuracy of site assessments using feedback from completed projects.

The long-term vision is to reduce the information and coordination costs that prevent homeowners from investigating feasible new housing supply.

---

## 19. Final project positioning

### Product tagline

**Button NZ — Unlock the housing hiding in your backyard.**

### Technical tagline

**Giving AI the ability to understand, design and reason about real physical spaces.**

### Hackathon pitch

Millions of homeowners have land that could potentially accommodate additional housing, but navigating site constraints, planning regulations, construction options and suppliers is complex and expensive.

Button NZ brings these disconnected processes together.

Using Meta's Muse and SAM models, geospatial evidence and Blender, our system examines real properties, reconstructs their physical environment, autonomously develops 3D housing concepts, checks supported constraints and connects proposals to actual prefab products.

Our technical innovation is an AI agent that can choose how to observe a physical site, program a 3D environment, evaluate its own work and revise designs in response to real-world evidence.

We're starting in New Zealand, where small-dwelling reforms create a timely opportunity, with the longer-term ambition of making additional housing easier to investigate and deliver wherever the same fundamental barriers exist.

### The one thing judges should remember

**We didn't just teach Meta's AI to draw houses. We gave it the tools to understand real land, design housing on it, discover when its design is wrong, and fix the problem.**

---

## 20. Primary references

- [Meta Global AI Developer Hackathon](https://dev.meta.ai/events/global-hackathon)
- [Cerebral Valley submission page](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit)
- [Meta Model API documentation](https://dev.meta.ai/docs/models)
- [Meta SAM 3.1 segmentation](https://dev.meta.ai/docs/media-segmentation)
- [Meta SAM 3D Objects repository](https://github.com/facebookresearch/sam-3d-objects)
- [Muse Glimmer post-training](https://dev.meta.ai/docs/muse-glimmer/post-training)
- [Muse Code](https://dev.meta.ai/docs/muse-code)
- [LINZ West Coast LiDAR dataset](https://data.linz.govt.nz/layer/d3Ytk7sCGn2fQS4/west-coast-lidar-point-cloud-2020-2025/)
- [NZ granny flat exemption guidance](https://www.building.govt.nz/projects-and-consents/planning-a-successful-build/scope-and-design/check-if-you-need-consents/building-work-that-doesnt-need-a-building-consent/granny-flats-exemption-guidance-and-resources)
- [National Environmental Standards for Detached Minor Residential Units](https://environment.govt.nz/acts-and-regulations/legislation/nes-dmru/)

**End of plan.**