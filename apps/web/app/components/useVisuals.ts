"use client";

import { type Dispatch, type SetStateAction, useEffect, useState } from "react";

import { type Job, getDesign } from "@/lib/api";

/** How many times to look for a design's AI visual while the API says it is
 * being made (about 30 s; it gives up within ~3 min at the default 2 s). */
export const VISUAL_POLLS = 90;

/** Polls every design in `chain` whose AI visual is still being made, not just
 * the newest: a design revised before its visual came still gets it. Each has
 * its own budget of polls. A failed poll only spends that budget: the visual
 * is extra, and never stops the page following its designs. */
export function useVisuals(
  chain: Job[],
  setChain: Dispatch<SetStateAction<Job[]>>,
  pollMs: number,
) {
  const [polls, setPolls] = useState<Record<string, number>>({});
  const waiting = chain
    .filter((j) => j.illustrating && (polls[j.id] ?? 0) < VISUAL_POLLS)
    .map((j) => j.id)
    .join(",");
  useEffect(() => {
    if (waiting === "") return;
    const timer = setTimeout(() => {
      const ids = waiting.split(",");
      setPolls((spent) => {
        const next = { ...spent };
        for (const id of ids) next[id] = (spent[id] ?? 0) + 1;
        return next;
      });
      for (const id of ids) {
        getDesign(id).then(
          (fresh) =>
            setChain((jobs) =>
              jobs.map((j) => (j.id === fresh.id ? fresh : j)),
            ),
          () => undefined, // counted above; the design itself is already shown
        );
      }
    }, pollMs);
    return () => clearTimeout(timer);
  }, [waiting, polls, pollMs, setChain]);
}
