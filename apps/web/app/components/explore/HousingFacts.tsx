"use client";

import type { HousingFact } from "@/lib/housingFacts";

import { useTurn } from "./useTurn";

const FACT_MS = 9000; // how long each fact is shown

/** Sourced facts about housing, one at a time, each with its source in
 * small type, and Reefton's beside the town screen's map. They turn with
 * the clock, so a fact shown again after an artifact carries on where they
 * left off rather than from the first. */
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
      className={`flex min-h-0 items-center gap-6 rounded-xl bg-white/5 ${large ? "flex-1 p-10" : "px-5 py-4"}`}
    >
      {/* Keyed by the fact, so each one fades in (not for less motion). */}
      <div key={fact.text} className="build-fade-in flex flex-1 flex-col gap-2">
        <p
          className={`font-medium text-white ${large ? "text-3xl leading-snug" : "text-xl"}`}
        >
          {fact.text}
        </p>
        <p className="text-xs text-zinc-400">Source: {fact.source}</p>
      </div>
      {fact.map && (
        // eslint-disable-next-line @next/next/no-img-element -- a report's own figure, with its legend
        <img
          src={fact.map}
          alt="The town screen's map of Reefton: each residential property coloured by whether a real prefab fits"
          className={`shrink-0 rounded-lg bg-white object-contain ${large ? "max-h-full w-2/5" : "h-28"}`}
        />
      )}
    </section>
  );
}
