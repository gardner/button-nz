# Button NZ: the product

**Unlock the housing hiding in your backyard.**

## The problem

Many New Zealand homeowners have room for a small second dwelling: a granny
flat for a parent, a studio for an adult child, a rental. Since 2026, a
detached dwelling of up to 70 m² can be built without a building consent if it
meets the conditions of Schedule 1A of the Building Act. Those conditions
include:

- 2 m from the title boundary and from other buildings;
- a single storey;
- at most 4 m high.

But an owner can't easily tell whether their section qualifies, or what would
fit. Today that means paying a designer or surveyor before knowing if the idea
is worth pursuing, and most people never start. Our property boundaries,
ground levels and aerial photos are public, open data, and they are enough to
answer the first question.

## What Button NZ does

An owner opens their property and, in one session:

1. **Sees what is there.** Button NZ reads the title, a 1 m LiDAR model of the
   ground and everything standing on it, and a 7.5 cm aerial photo. Meta's
   SAM 3.1 picks out the sheds, trees and garden beds, and each is checked
   against the LiDAR heights. Where the photo and the LiDAR disagree, the owner
   is asked, not guessed for.
2. **Says what matters.** The owner confirms which things are buildings,
   which areas to keep clear (the big tree, the vegetable garden), and that
   the list is complete.
3. **Describes what they want**, in their own words: "a small one-bedroom
   studio that keeps the trees and gets the afternoon sun."
4. **Gets a checked concept.**
   - Meta's Muse Spark looks at the site through LiDAR views it chooses
     itself: slopes, contours, cross-sections. It then designs the dwelling
     by writing a program for Blender, a professional 3D tool.
   - An independent evaluator measures the result: setbacks, separation from
     the confirmed buildings, floor area, height, floor level above the
     ground, and the keep-clear areas.
   - If a check fails, Muse sees the measurements and its own render, and
     fixes the design.
   - The owner gets the accepted concept in 3D, with every check and the rule
     behind it.
5. **Changes it in plain words**, "move it 3 m further from the street", and
   compares before and after. Every revision is checked again.

## Why it can be trusted

- **Measured, not imagined.** The site comes from surveyed open data with
  stated sources, licences and capture dates. The design is real geometry in a
  real 3D tool, not a picture.
- **The AI can't argue a check away.** The evaluator is ordinary code that
  measures the model's geometry. A failed check stays failed, whatever the
  model says.
- **Honest about what it doesn't know.** A check it can't decide, such as an
  unconfirmed boundary line or an existing building nobody has confirmed, is
  reported as "unknown", never as a pass.
- **Safe to run.** Model-written code runs in a locked-down sandbox, with no
  network and no secrets.

## Where it goes next

- **Matching real products:** match a concept to real prefab products, and to
  the professionals a project needs next (a surveyor, a designer, the council).
- **More of the country:** more councils and more rules. Wherever the LiDAR
  and parcel data exist, the pipeline already works.
- **Handover:** a package for a designer or the council, with the evidence,
  the chosen concept and the open questions.

The aim is to take the cost and guesswork out of the first step, so more
owners find out what their land could hold.
