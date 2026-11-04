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

/** The live views as seen from one look at the job to the next: which were
 * there, which view Muse was last seen asking for, and the tool of each view
 * whose ask was seen. */
export interface ViewWatch {
  seen: readonly string[];
  asked: string | null;
  names: ReadonlyMap<string, string>;
}

export const NO_VIEWS: ViewWatch = { seen: [], asked: null, names: new Map() };

/** The live views' tools, from one more look at the job. The API lists a
 * running attempt's views without saying which tool drew each, but it says
 * which one Muse is asking for while it is drawn. A view is named only when
 * that is sure: it is the only one to land since Muse was seen asking. Some
 * asks draw nothing (exact heights are words), and an ask between two looks
 * is unseen; for a later view to take that name, Muse would have to answer
 * between two looks (1.5 s apart), which a model call doesn't. */
export function watchViews(watch: ViewWatch, live: Live | null): ViewWatch {
  const now = live?.observations ?? [];
  const landed = now.filter((src) => !watch.seen.includes(src));
  const names = new Map(watch.names);
  if (watch.asked !== null && landed.length === 1)
    names.set(landed[0], watch.asked);
  return {
    seen: now,
    asked: live?.phase === "observing" ? live.detail : null,
    names,
  };
}
