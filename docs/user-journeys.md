# User journeys

Who uses Button NZ, what they come for, and each journey step by step through
the app at https://button.nz. The features named here are listed in
[features.md](features.md); the page's layout is in
[information-architecture.md](information-architecture.md).

## Who it is for

| Person | Wants | Knows |
|---|---|---|
| **The owner** | To find out whether their section can take a granny flat, what would fit, and what it would take, before paying anyone | Their section, and what they want from it. Not the Building Act, LiDAR or Blender |
| **A judge or visitor** | To see quickly that it works, on a real site, and how far to trust it | Software and AI, maybe not New Zealand's rules |
| **The team** | To run it, keep it honest, and record and package what it does | All of it |

A designer, a supplier or the council would come next: the product points the
owner to them, and doesn't yet serve them directly ([product.md](product.md)).

## 1. The owner says what's on their section

**Goal:** the designs are checked against what really stands on the land.

1. The owner opens button.nz and sees their section: the title, the parcels
   on the aerial photo, and where each dataset comes from and when it was
   captured.
2. Under "What is on the site", each card is something SAM 3.1 found on the
   photo, with its area and height from the LiDAR. Where the photo and the
   LiDAR disagree, the card asks for their judgement.
3. For each one they choose **Existing building**, **Keep clear** (a tree to
   keep, the vegetable garden) or **Ignore**.
4. They tick **Every building on the site is listed**.
5. The team fixes the survey as the owner decided it. From then on every
   design is checked against it, and visitors see who decided it.

**What can go wrong:** the photo (2024–25) and the LiDAR (2020–24) are older
than the site. The owner's word is what counts. A feature left undecided
constrains nothing, and "buildings complete" unticked leaves separation
"unknown" in every design.

## 2. The owner gets a checked concept

**Goal:** a concept for their own brief that meets the exemption's rules,
with the evidence.

1. They write a brief in their own words: "A small one-bedroom studio that
   gets the afternoon sun and keeps the trees." They leave "Let the model
   request LiDAR views" on.
2. They press **Design**. The page shows the design queued, then running.
3. Muse Spark looks at the site through the LiDAR views it asks for, writes a
   Blender script, and sandboxed Blender builds and measures it. Each attempt
   appears as it finishes, with its render and every check.
4. If a check fails ("0.50 m from the boundary; at least 2 m required"),
   Muse sees that measurement and its own render, and tries again, up to
   three attempts.
5. The status line says **Accepted: attempt n**. Each check shows pass, fail
   or unknown, its measurement and the rule it comes from.
6. A few seconds later the AI illustration appears, labelled AI-illustrated,
   shown only because SAM 3.1 found the house kept the design's shape.
7. **View in 3D** shows the design on the site's terrain.

**What can go wrong:**
- No attempt passes ("No attempt passed every check"), and the attempts show
  why.
- The run fails outright ("The design run failed: …"), with the reason.
- The server refuses to start it, because the day's 30 design runs are used.
  The page says when the next frees up, and keeps the design already on show.
- An "unknown" check doesn't stop acceptance but is shown, for the owner to
  settle with a professional.

Typical time: two to five minutes.

## 3. The owner changes it

**Goal:** the concept they want, still checked.

1. Under the accepted design, in **Change this design**, they write "Move it
   3 m further from the street" and press **Revise**.
2. Muse starts from the accepted script and makes the change. The evaluator
   checks it again, from scratch.
3. The design history lists the original and the revision. The revision is
   shown **before and after**, beside the design it changed.
4. They can revise the revision, or select any earlier step and change that
   instead.

**What can go wrong:** a revision that breaks a rule isn't accepted. The
design it changed stays in the history to go back to.

## 4. The owner finds a real prefab, and places it

**Goal:** a product they can actually buy, on their section, checked.

1. Under an accepted design they press **Which real prefabs fit?**
2. They see the prefabs whose published outside footprint fits inside the
   design's walls, largest first:
   - size, floor area and its basis, and bedrooms and bathrooms;
   - the price, or "not published";
   - what the price leaves out, and what the supplier says about the West
     Coast.

   Products that can't be checked are named apart.
3. They press **Place it on the site** on one: say, the AirHome Vista.
4. A new design starts, with the same brief and the walls fixed to the
   Vista's 12.2 × 4 m. The page says "Placing the AirHome Vista: walls
   12.2 × 4 m".
5. Muse chooses where and which way round. The evaluator checks first that
   the walls are the Vista's footprint, then every other rule.
6. Under **Next steps** they see what comes next:
   - a PIM from Buller District Council;
   - a licensed designer and builder;
   - a ground test;
   - certifying plumbers, drainlayers and electricians;
   - the records they give the council within 20 working days of completion.

   The link opens the sourced list of local firms in
   [suppliers.md](suppliers.md).

**What can go wrong:** nothing fits the design's walls, and the panel says so.
A product whose plan isn't a rectangle (Lockwood Ara) can't be placed, and
says why. The placed design is checked with the eaves Muse draws, because
suppliers mostly don't publish theirs.

## 5. A judge sees it work

**Goal:** within a minute, a real result and a reason to trust it. Within ten,
one of their own.

1. The judge opens a link to a finished design (`button.nz/?design=<id>`).
   The design and its revisions are already there: every attempt, every
   check, the 3D model, the AI visual, before and after.
2. They read the site panel: real parcels, real LiDAR, sources and capture
   dates. They see the survey as the owner decided it, and who decided it.
3. They write their own brief and press **Design**, and watch it run live:
   Muse's LiDAR views, a failed check and its repair, the accepted design.
4. They ask which prefabs fit, and place one.
5. For depth they turn to the [README](../README.md) (how it works, the Meta
   models) and [docs/results](results/README.md):
   - the experiments, from live runs: one shot against feedback, and the
     photo alone against Muse's own LiDAR views;
   - the town screen: 762 of Reefton's 1,320 residential sections have room
     for a real prefab.

**What can go wrong:** the day's 30 design runs are used, and the page says
when the next frees up; the finished designs stay open to read. The survey is
fixed, so a judge can't change what other judges' designs are checked
against.

## 6. The team runs and records it

**Goal:** a server that stays up and stays honest, and a submission built
from real runs.

1. **Serve it:**
   - `scripts/deploy/install.sh` builds the app and writes the settings and
     systemd services, adding the Cloudflare tunnel once its token is there.
   - `check.sh` checks the served URL as a visitor reaches it.
   - Details are in [deploy.md](deploy.md).
2. **Fix the survey** once the owner has decided it: set
   `BUTTON_SURVEY_DECIDED_BY` and run `install.sh` again.
3. **Record the demo:**
   - `scripts/demo/record.py` drives the live app: the owner's survey, a
     brief, the design, its visual and 3D model, a revision, the prefabs,
     and a placement.
   - `cut.py` cuts it to length, with the speed shown wherever it's sped up.
4. **Package the sample:** `python -m button_nz.sample` packs the final
   take's design and revisions, with the survey they were checked against,
   and refuses anything partial.
5. **Measure:** the benchmarks in `button_nz.bench` rerun the experiments and
   the town screen; each writes its report from its own log.

**What can go wrong:** something fails, and it stops rather than falling back:
- a survey that isn't the owner's fails the recording before any paid call;
- a design without its survey record can't be packaged;
- a tool missing from the PATH stops the install.
