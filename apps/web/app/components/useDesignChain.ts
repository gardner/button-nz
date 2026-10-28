"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  type Job,
  createDesign,
  getDesign,
  reviseDesign,
} from "@/lib/api";

/** How many more times to look for an accepted design's AI visual while the
 * API says it is being made (about 30 s; it gives up within ~3 min). */
const VISUAL_POLLS = 90;

/** Whether `newest` is still being designed (`working`, which holds up the
 * forms), and whether to poll it (`active`): also while its visual is being
 * made, until `spent` polls use up its budget. Looking for a visual doesn't
 * hold up the forms: the design is already usable. */
function following(newest: Job | undefined, lost: boolean, spent: number) {
  const working =
    !lost && (newest?.status === "queued" || newest?.status === "running");
  const looking =
    !lost && newest?.illustrating === true && spent < VISUAL_POLLS;
  return { working, active: working || looking };
}

/** The designs made on this page: an original, then each revision in the
 * order it was asked for. The newest is polled until it is done or failed.
 * A transient poll failure is shown and retried; a permanent one (the API no
 * longer has the job) stops polling. One design is started at a time.
 * The design shown is the newest unless an earlier step is selected. A done
 * job is polled a while longer if its AI visual is still being made; the
 * forms stay usable meanwhile. */
export function useDesignChain(pollMs: number) {
  const [chain, setChain] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const starting = useRef(false); // guards clicks before the re-render disables the forms
  const [lost, setLost] = useState(false); // the API can't give the newest job any more
  // Polls spent looking for a done job's visual: each job has its own budget.
  const [visualPolls, setVisualPolls] = useState({ id: "", n: 0 });
  const newest = chain.at(-1);
  const spent = visualPolls.id === newest?.id ? visualPolls.n : 0;
  const { working, active } = following(newest, lost, spent);
  useEffect(() => {
    if (!active || newest === undefined) return;
    const timer = setTimeout(() => {
      getDesign(newest.id).then(
        (next) => {
          setProblem(null);
          if (next.status === "done")
            setVisualPolls((p) => ({
              id: next.id,
              n: p.id === next.id ? p.n + 1 : 1,
            }));
          setChain((jobs) => jobs.map((j) => (j.id === next.id ? next : j)));
        },
        (e: Error) => {
          setProblem(e.message);
          if (e instanceof ApiError && !e.transient) setLost(true);
          else setRetries((n) => n + 1);
        },
      );
    }, pollMs);
    return () => clearTimeout(timer);
  }, [active, newest, pollMs, retries]);

  /** Send `request` unless one is already on its way; `follow` adds the job
   * it returns to the chain. */
  function begin(request: () => Promise<Job>, follow: (job: Job) => void) {
    if (starting.current) return;
    starting.current = true;
    setSubmitting(true);
    setProblem(null);
    request()
      .then(
        (job) => {
          setLost(false);
          setSelected(null); // show the new design
          follow(job);
        },
        (e: Error) => setProblem(e.message),
      )
      .finally(() => {
        starting.current = false;
        setSubmitting(false);
      });
  }

  /** Start a new design, leaving the old chain behind. */
  function design(brief: string, observe: boolean) {
    if (starting.current) return;
    setChain([]); // stop following the old chain before the new one exists
    begin(
      () => createDesign(brief, observe),
      (job) => setChain([job]),
    );
  }

  /** Change `parent`'s accepted design, observing as it did. The chain keeps
   * every earlier step, so a failed revision leaves them all to go back to. */
  function revise(parent: Job, instruction: string) {
    begin(
      () => reviseDesign(parent.id, instruction, parent.allowObservations),
      (job) => setChain((jobs) => [...jobs, job]),
    );
  }

  const shown = chain.find((j) => j.id === selected) ?? newest;
  return {
    chain,
    shown,
    select: setSelected,
    problem,
    busy: submitting || working,
    design,
    revise,
  };
}
