"use client";

import { useEffect, useState } from "react";

import type { HousingFact } from "@/lib/housingFacts";

const FACT_MS = 9000; // how long each fact is shown

/** Sourced facts about housing, one at a time, each with its source in
 * small type. They turn with the clock, so a fact shown again after an
 * artifact carries on where they left off rather than from the first. */
export function HousingFacts({
  facts,
  large = false,
}: {
  facts: readonly HousingFact[];
  large?: boolean; // the stage's whole: there is nothing else to show yet
}) {
  const turn = useTurn(FACT_MS);
  const fact = facts[turn % facts.length];
  if (!fact) return null;
  return (
    <section
      aria-label="Housing facts"
      className={`flex flex-col gap-2 rounded-xl bg-white/5 ${large ? "flex-1 justify-center p-10" : "px-5 py-4"}`}
    >
      {/* Keyed by the fact, so each one fades in (not for less motion). */}
      <div key={fact.text} className="build-fade-in flex flex-col gap-2">
        <p
          className={`font-medium text-white ${large ? "text-3xl leading-snug" : "text-xl"}`}
        >
          {fact.text}
        </p>
        <p className="text-xs text-zinc-400">Source: {fact.source}</p>
      </div>
    </section>
  );
}

/** Which turn of `ms` the clock is in, moving on at each turn's end. */
function useTurn(ms: number): number {
  const [turn, setTurn] = useState(() => Math.floor(Date.now() / ms));
  useEffect(() => {
    // Never the same turn again: a timer that fires a moment early would
    // otherwise stop the facts turning.
    const timer = setTimeout(
      () => setTurn((t) => Math.max(t + 1, Math.floor(Date.now() / ms))),
      ms - (Date.now() % ms),
    );
    return () => clearTimeout(timer);
  }, [turn, ms]);
  return turn;
}
