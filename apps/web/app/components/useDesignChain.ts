"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  type Job,
  createDesign,
  getDesign,
  reviseDesign,
} from "@/lib/api";

import { useVisuals } from "./useVisuals";

/** The designs made on this page: an original, then each revision in the
 * order it was asked for. The newest is polled until it is done or failed.
 * A transient poll failure is shown and retried; a permanent one (the API no
 * longer has the job) stops polling. One design is started at a time.
 * The design shown is the newest unless an earlier step is selected. AI
 * visuals still being made are followed separately (`useVisuals`), and the
 * forms don't wait for them. A page opened with `?design=<id>` starts with
 * that design and the designs it revises, and the address bar keeps the id of
 * the design on show, so it can be shared. With `siteId`, new designs are
 * made on that site (else the demo site). */
export function useDesignChain(pollMs: number, siteId?: string) {
  const [chain, setChain] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const starting = useRef(false); // guards clicks before the re-render disables the forms
  const [lost, setLost] = useState(false); // the API can't give the newest job any more
  const newest = chain.at(-1);
  const working =
    !lost && (newest?.status === "queued" || newest?.status === "running");
  useVisuals(chain, setChain, pollMs);
  useEffect(() => {
    const linked = new URLSearchParams(window.location.search).get("design");
    if (linked === null) return;
    lineage(linked).then(
      (jobs) => {
        if (siteId !== undefined && jobs.at(-1)?.siteId !== siteId) {
          // A design on another site isn't this site's to show; its link goes,
          // unless a newer design has taken its place meanwhile.
          const still = new URLSearchParams(window.location.search).get(
            "design",
          );
          if (still === linked) dropLink();
          return;
        }
        setChain((started) => (started.length ? started : jobs));
      },
      (e: Error) => {
        // A newer design has taken the link's place: its failure is old news.
        const still = new URLSearchParams(window.location.search).get("design");
        if (still === linked)
          setProblem(`Could not open design ${linked}: ${e.message}`);
      },
    );
  }, [siteId]); // fixed for a mount: the page remounts this for each site
  useEffect(() => {
    if (!working || newest === undefined) return;
    const timer = setTimeout(() => {
      getDesign(newest.id).then(
        (next) => {
          setProblem(null);
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
  }, [working, newest, pollMs, retries]);

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

  /** Start a new design, leaving the old chain behind once it exists; with
   * `productId`, one that places that catalogue product. A refused request
   * (say, the daily cap) keeps the chain on show. */
  function design(brief: string, observe: boolean, productId?: string) {
    begin(
      () => createDesign(brief, observe, productId, siteId),
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
  const shownId = shown?.id;
  useEffect(() => {
    if (shownId === undefined) return;
    const url = new URL(window.location.href);
    url.searchParams.set("design", shownId);
    window.history.replaceState(null, "", url);
  }, [shownId]);
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

/** Takes `?design=` out of the address bar. */
function dropLink() {
  const url = new URL(window.location.href);
  url.searchParams.delete("design");
  window.history.replaceState(null, "", url);
}

/** Design `id`, after the designs it revises, oldest first. */
async function lineage(id: string): Promise<Job[]> {
  const jobs: Job[] = [];
  for (let next: string | null = id; next !== null; next = jobs[0].parentId) {
    jobs.unshift(await getDesign(next));
  }
  return jobs;
}
