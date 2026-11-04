"use client";

import { useState } from "react";

import type { Job, Live } from "@/lib/api";
import { NO_VIEWS, watchViews } from "@/lib/museStage";

import { Elapsed, Filmstrip, Steps } from "./MuseParts";
import { MuseOverlay } from "./MuseOverlay";
import type { Place } from "./MuseSiteShots";
import { PrefabsMeanwhile } from "./PrefabsMeanwhile";

/** The run itself while a design is made: large over the screen, each step's
 * work as it lands, until the owner hides it (× ) back to the small panel
 * beside the map. It opens only for a design that is running when shown,
 * and stays to show the accepted design and its visual. Give it
 * `key={job.id}`: each design starts afresh. */
export function MuseAtWork({ job, place }: { job: Job; place: Place }) {
  const working = job.status === "queued" || job.status === "running";
  const [large, setLarge] = useState(working);
  const names = useViewNames(job.live);
  if (large)
    return (
      <MuseOverlay
        job={job}
        names={names}
        place={place}
        onHide={() => setLarge(false)}
      />
    );
  if (!working) return null;
  // Below the top bar like the column on the left (5rem), scrolling on a
  // short screen rather than covering the steps and the 2D/3D switch.
  return (
    <div className="xl:fixed xl:bottom-4 xl:right-4 xl:z-10 xl:max-h-[calc(100dvh-6rem)] xl:w-[400px] xl:overflow-y-auto">
      <MusePanel job={job} onEnlarge={() => setLarge(true)} />
    </div>
  );
}

/** The live views' tools, from each look at the job (`watchViews`). */
function useViewNames(live: Live | null): ReadonlyMap<string, string> {
  const [watch, setWatch] = useState(() => watchViews(NO_VIEWS, live));
  const [looked, setLooked] = useState(live);
  if (live !== looked) {
    setLooked(live);
    setWatch(watchViews(watch, live));
  }
  return watch.names;
}

/** The small panel: the step the run is on, lit, and a filmstrip of what it
 * has made so far, every image real (the LiDAR views given with the brief
 * and those Muse asked for, each attempt's render with its verdict). */
function MusePanel({ job, onEnlarge }: { job: Job; onEnlarge: () => void }) {
  const live = job.live;
  return (
    <section
      aria-label="Muse at work"
      className="flex flex-col gap-3 rounded-2xl bg-zinc-950/90 p-4 text-white shadow-2xl backdrop-blur"
    >
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Muse at work</h2>
        <span className="flex items-baseline gap-3">
          <Elapsed since={job.startedAt} />
          <button
            type="button"
            onClick={onEnlarge}
            className="rounded-full px-2 text-xs text-zinc-300 ring-1 ring-white/20 hover:bg-white/10 hover:text-white"
          >
            Show large
          </button>
        </span>
      </header>
      {live ? (
        <>
          <p className="text-sm text-zinc-300">Attempt {live.attempt}</p>
          <Steps phase={live.phase} detail={live.detail} />
        </>
      ) : (
        <p className="text-sm text-emerald-300 motion-safe:animate-pulse">
          {waitingWords(job)}
        </p>
      )}
      <Filmstrip attempts={job.attempts} live={live} />
      <PrefabsMeanwhile />
    </section>
  );
}

function waitingWords(job: Job): string {
  return job.status === "queued"
    ? "Waiting for a free designer…"
    : "Getting the site ready…";
}
