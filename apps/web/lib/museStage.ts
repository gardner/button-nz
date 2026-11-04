/**
 * What the "Muse at work" overlay shows large, chosen from the design job the
 * API returns: one thing at a time, in the order the run makes them.
 */

import type { Attempt, Job, Live } from "./api";

/** The one thing on the stage. Later work adds a case here (the placement
 * candidates, #167; Muse's script as it streams, #165), and the overlay's
 * switch over `kind` won't compile until it draws it. */
export type Stage =
  | { kind: "waiting"; queued: boolean } // no step yet: queued, or starting
  | { kind: "thinking" } // Muse's first move, nothing made yet
  | { kind: "reading"; tool: string } // a LiDAR view Muse asked for, being drawn
  | { kind: "view"; src: string; number: number; tool: string | null } // the newest view, Muse reading it
  | { kind: "fixing"; attempt: Attempt } // the attempt that failed, Muse writing the next
  | { kind: "building" } // Blender building and rendering the script
  | { kind: "measuring" } // the evaluator measuring the rules
  | {
      kind: "accepted";
      attempt: Attempt;
      visual: string | null;
      illustrating: boolean;
    }
  | { kind: "stopped"; attempt: Attempt | null; error: string | null }; // done, nothing accepted

/** What is on the stage now; `names` are the live views' tools, as watched. */
export function stageOf(job: Job, names: ReadonlyMap<string, string>): Stage {
  if (job.status === "done" || job.status === "failed") return finished(job);
  const live = job.live;
  if (!live) return { kind: "waiting", queued: job.status === "queued" };
  switch (live.phase) {
    case "observing":
      return { kind: "reading", tool: live.detail };
    case "rendering":
      return { kind: "building" };
    case "checking":
      return { kind: "measuring" };
    case "thinking":
      return thinking(job, live, names);
  }
}

function finished(job: Job): Stage {
  const accepted = job.attempts.find((a) => a.number === job.acceptedAttempt);
  if (accepted)
    return {
      kind: "accepted",
      attempt: accepted,
      visual: accepted.files["visual.png"] ?? null,
      illustrating: job.illustrating,
    };
  return {
    kind: "stopped",
    attempt: job.attempts.at(-1) ?? null,
    error: job.error,
  };
}

/** While Muse thinks: the newest view of this attempt (it is reading it), or
 * else the attempt before, which failed (it is fixing it). */
function thinking(
  job: Job,
  live: Live,
  names: ReadonlyMap<string, string>,
): Stage {
  const newest = live.observations.at(-1);
  if (newest !== undefined)
    return {
      kind: "view",
      src: newest,
      number: viewNumber(newest),
      tool: names.get(newest) ?? null,
    };
  const failed = job.attempts.find((a) => a.number === live.attempt - 1);
  return failed ? { kind: "fixing", attempt: failed } : { kind: "thinking" };
}

/** A view's number in its attempt: observation-<n>.png is the n-th thing
 * Muse asked to see (some asks draw nothing, so numbers can skip). */
function viewNumber(src: string): number {
  return Number(/observation-(\d+)\.png$/.exec(src)?.[1]);
}

/** An ask for a view, in the attempt it was made in (each attempt numbers
 * its views from 1). */
interface Ask {
  tool: string;
  attempt: number;
}

/** The live views as seen from one look at the job to the next: which were
 * there, the ask Muse was seen making, the ask whose view is still to land
 * (with the newest view number there before it), and the tool of each view
 * whose ask was seen. */
export interface ViewWatch {
  seen: readonly string[];
  observing: Ask | null;
  asked: (Ask & { after: number }) | null;
  names: ReadonlyMap<string, string>;
}

export const NO_VIEWS: ViewWatch = {
  seen: [],
  observing: null,
  asked: null,
  names: new Map(),
};

/** The live views' tools, from one more look at the job. The API lists a
 * running attempt's views without saying which tool drew each, but it says
 * which one Muse is asking for while it is drawn. A view is named only when
 * that is sure: it is the only one to land since the ask was seen, in the
 * same attempt, and its number is the next after the newest view there then.
 * observation-<n>.png is the attempt's n-th ask, and asks that draw nothing
 * (exact heights are words, or an ask that failed) still count, so an ask
 * unseen between two looks, however far apart the looks are, shows as a
 * skipped number, and its view is left unnamed. */
export function watchViews(watch: ViewWatch, live: Live | null): ViewWatch {
  const now = live?.observations ?? [];
  const landed = now.filter((src) => !watch.seen.includes(src));
  const asked = watch.asked;
  const its = asked && askedFor(asked, live, landed);
  const names = new Map(watch.names);
  if (asked && its) names.set(its, asked.tool);
  const observing =
    live?.phase === "observing"
      ? { tool: live.detail, attempt: live.attempt }
      : null;
  return {
    seen: now,
    observing,
    asked: nextAsk(watch, observing, now, landed, its),
    names,
  };
}

/** The view `asked` drew, if one landed that can only be its: alone, in the
 * same attempt, and numbered next after the newest view there at the ask. */
function askedFor(
  asked: NonNullable<ViewWatch["asked"]>,
  live: Live | null,
  landed: readonly string[],
): string | null {
  const [view] = landed;
  return live?.attempt === asked.attempt &&
    landed.length === 1 &&
    viewNumber(view) === asked.after + 1
    ? view
    : null;
}

/** The ask whose view is still to land, after one more look. */
function nextAsk(
  watch: ViewWatch,
  observing: Ask | null,
  now: readonly string[],
  landed: readonly string[],
  its: string | null, // the view just named as the last ask's
): ViewWatch["asked"] {
  if (observing === null) return null;
  const same =
    watch.observing?.tool === observing.tool &&
    watch.observing.attempt === observing.attempt;
  if (same)
    // The same ask, still drawn: once a view lands, it is spent (or unsure).
    return landed.length === 0 ? watch.asked : null;
  // A new ask: a view landing with it, not the last ask's, may be its own.
  if (landed.some((src) => src !== its)) return null;
  return { ...observing, after: Math.max(0, ...now.map(viewNumber)) };
}
