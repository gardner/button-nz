"use client";

import { useEffect, useId, useState } from "react";

import {
  type BBox,
  type BuildProgress,
  type Ring,
  type Square,
  getProgress,
  placed,
  ringPath,
  squareFrame,
} from "@/lib/progress";
import type { SiteState, SiteStatus, SiteStep } from "@/lib/sites";

import { STEPS } from "./BuildProgress";

/** Each survey concept's colour: structures warm, plants green, paving grey. */
const CONCEPT_COLOURS: Record<string, string> = {
  building: "#f97316",
  shed: "#facc15",
  tree: "#22c55e",
  hedge: "#84cc16",
  "garden bed": "#c084fc",
  driveway: "#a1a1aa",
  path: "#e4e4e7",
  car: "#38bdf8",
};
const OTHER_CONCEPT = "#22d3ee";
const READY_HOLD_MS = 3000; // how long "Site ready" stays before stepping aside

/** The build of a site opened while it was building, shown step by step
 * until a moment after it is ready, or until the owner hides it. Give it
 * `key={site.id}`: each site starts open only if it is building, and opens
 * again whenever it is built again. */
export function SiteBuildView({
  site,
  pollMs,
  readyHoldMs = READY_HOLD_MS,
}: {
  site: SiteState;
  pollMs: number;
  readyHoldMs?: number;
}) {
  const building = site.status === "building";
  const [open, setOpen] = useState(building);
  // A site that stopped and is built again (a retry keeps its id) opens
  // again; one dismissed stays hidden while the same build goes on.
  const [wasBuilding, setWasBuilding] = useState(building);
  if (building !== wasBuilding) {
    setWasBuilding(building);
    if (building) setOpen(true);
  }
  const { progress, problem } = useProgress(
    open ? site.id : null,
    building,
    pollMs,
  );
  const ready = site.status === "ready";
  useEffect(() => {
    if (!open || !ready) return;
    const timer = setTimeout(() => setOpen(false), readyHoldMs);
    return () => clearTimeout(timer);
  }, [open, ready, readyHoldMs]);
  if (!open) return null;
  return (
    <BuildOverlay
      status={site.status}
      step={site.step}
      error={site.error ?? problem}
      progress={progress}
      onDismiss={() => setOpen(false)}
    />
  );
}

/** The build's progress, asked for every `pollMs` while it builds, and once
 * more when it stops, for the last step's work. */
function useProgress(siteId: string | null, building: boolean, pollMs: number) {
  const [shown, setShown] = useState<{
    id: string;
    progress: BuildProgress;
  } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    if (siteId === null) return;
    let gone = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const again = () => {
      if (building) timer = setTimeout(ask, pollMs);
    };
    const ask = () =>
      getProgress(siteId).then(
        (progress) => {
          if (gone) return;
          setShown({ id: siteId, progress });
          setProblem(null);
          again();
        },
        (e: Error) => {
          if (gone) return;
          setProblem(`Couldn't show the build's progress: ${e.message}`);
          again();
        },
      );
    ask();
    return () => {
      gone = true;
      clearTimeout(timer);
    };
  }, [siteId, building, pollMs]);
  return {
    progress: shown?.id === siteId ? shown.progress : null,
    problem,
  };
}

/** A large square over the map's corner: each step's work as it arrives,
 * all in one frame, so the parcels, the LiDAR, the photo and SAM's finds
 * line up. */
export function BuildOverlay({
  status,
  step,
  error,
  progress,
  onDismiss,
}: {
  status: SiteStatus;
  step: SiteStep | null;
  error: string | null;
  progress: BuildProgress | null;
  onDismiss: () => void;
}) {
  // What SAM 3.1 is being asked, only while the build goes on: one that
  // stopped partway through the survey asks nothing more.
  const asking = status === "building" ? askingNow(progress) : null;
  return (
    <section
      aria-label="Your site, as it is built"
      className="pointer-events-auto absolute right-6 bottom-6 z-20 flex w-[min(46vh,40vw)] min-w-64 flex-col gap-2 rounded-2xl bg-zinc-950/75 p-3 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur"
    >
      <header className="flex items-start justify-between gap-3">
        <p aria-live="polite" className="text-sm font-medium">
          {caption(status, step)}
        </p>
        <button
          type="button"
          aria-label="Hide"
          onClick={onDismiss}
          className="-mt-1 -mr-1 rounded-full px-2 text-lg leading-7 text-zinc-400 hover:bg-white/10 hover:text-white"
        >
          ×
        </button>
      </header>
      {error && <p className="text-xs text-zinc-300">{error}</p>}
      <Picture progress={progress} asking={asking} />
      {progress && <Legend progress={progress} asking={asking} />}
    </section>
  );
}

function askingNow(progress: BuildProgress | null): string | null {
  return progress?.survey?.asking ?? null;
}

/** The square every step is drawn in; until the parcels are found there is
 * nothing to draw, and it waits, alive. */
function Picture({
  progress,
  asking,
}: {
  progress: BuildProgress | null;
  asking: string | null;
}) {
  const frame = progress?.frame ?? null;
  const square = frame ? squareFrame(frame) : null;
  return (
    <svg
      viewBox={square ? `0 0 ${square.side} ${square.side}` : "0 0 1 1"}
      className={`aspect-square w-full rounded-xl bg-zinc-900/60 ${
        square ? "" : "motion-safe:animate-pulse"
      }`}
      aria-hidden
    >
      {progress && frame && square && (
        <Layers
          progress={progress}
          frame={frame}
          square={square}
          asking={asking}
        />
      )}
    </svg>
  );
}

function caption(status: SiteStatus, step: SiteStep | null): string {
  if (status === "ready") return "Site ready";
  if (status === "no_lidar") return "No LiDAR here yet";
  if (status === "failed") return "Couldn't build this site";
  const doing = STEPS.find((s) => s.key === step)?.doing;
  return doing ? `${doing}…` : "Starting…";
}

/** Every step's work, clipped to the frame the LiDAR and photo cover: the
 * outlines around the site reach past it. */
function Layers({
  progress,
  frame,
  square,
  asking,
}: {
  progress: BuildProgress;
  frame: BBox;
  square: Square;
  asking: string | null;
}) {
  const { terrain, aerial, survey } = progress;
  const clip = useId();
  return (
    <g data-layer="frame" clipPath={`url(#${clip})`}>
      <clipPath id={clip}>
        <rect {...placed(frame, square)} />
      </clipPath>
      {terrain && (
        <image
          data-layer="terrain"
          href={terrain.url}
          preserveAspectRatio="none"
          className="build-fade-in"
          {...placed(terrain.bbox, square)}
        />
      )}
      {aerial && (
        <image
          data-layer="aerial"
          href={aerial.url}
          preserveAspectRatio="none"
          opacity={0.9}
          className="build-fade-in"
          {...placed(aerial.bbox, square)}
        />
      )}
      <Rings
        name="buildings"
        rings={progress.buildings}
        square={square}
        colour="#e4e4e7"
        fill={0.08}
      />
      {survey?.found.map((f) => (
        <Rings
          key={f.concept}
          name={`found-${f.concept}`}
          rings={f.rings}
          square={square}
          colour={CONCEPT_COLOURS[f.concept] ?? OTHER_CONCEPT}
          fill={0.3}
        />
      ))}
      <Rings
        name="parcels"
        rings={progress.parcels}
        square={square}
        colour="#ffffff"
        fill={0}
        drawn
      />
      {asking && <Scan side={square.side} />}
    </g>
  );
}

function Rings({
  name,
  rings,
  square,
  colour,
  fill,
  drawn = false,
}: {
  name: string;
  rings: Ring[];
  square: Square;
  colour: string;
  fill: number;
  drawn?: boolean; // drawn on, as a pen would
}) {
  // A dash is measured on screen once a stroke stops scaling, so a line that
  // is drawn on is sized in metres instead: about 2.5 px across the square.
  return (
    <g
      data-layer={name}
      stroke={colour}
      fill={colour}
      fillOpacity={fill}
      strokeWidth={drawn ? square.side * 0.007 : 1.25}
      className="build-fade-in"
    >
      {rings.map((ring, i) => (
        <path
          key={i}
          d={ringPath(ring, square)}
          vectorEffect={drawn ? undefined : "non-scaling-stroke"}
          pathLength={drawn ? 1 : undefined}
          className={drawn ? "build-draw-on" : undefined}
        />
      ))}
    </g>
  );
}

/** A line sweeping the photo while SAM 3.1 looks it over. */
function Scan({ side }: { side: number }) {
  return (
    <g data-layer="scan" className="build-scan">
      <rect
        x={0}
        y={-side * 0.08}
        width={side}
        height={side * 0.08}
        fill="url(#build-scan-trail)"
      />
      <rect x={0} y={0} width={side} height={side * 0.006} fill="#67e8f9" />
      <defs>
        <linearGradient id="build-scan-trail" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#67e8f9" stopOpacity={0} />
          <stop offset="1" stopColor="#67e8f9" stopOpacity={0.35} />
        </linearGradient>
      </defs>
    </g>
  );
}

function Legend({
  progress,
  asking,
}: {
  progress: BuildProgress;
  asking: string | null;
}) {
  const { terrain, survey } = progress;
  const found = new Map(survey?.found.map((f) => [f.concept, f.rings.length]));
  return (
    <div className="flex flex-col gap-1.5 text-xs text-zinc-300">
      {terrain && (
        <p>
          LiDAR surface: {Math.round(terrain.lowM)}–{Math.round(terrain.highM)}{" "}
          m above sea level
        </p>
      )}
      {survey && (
        <ul className="flex flex-wrap gap-1.5">
          {survey.concepts.map((concept) => {
            const state = found.has(concept)
              ? "done"
              : concept === asking
                ? "asking"
                : "todo";
            return (
              <li
                key={concept}
                data-state={state}
                className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 ${
                  state === "done"
                    ? "bg-white/10 text-white"
                    : state === "asking"
                      ? "animate-pulse bg-cyan-400/20 text-cyan-100 ring-1 ring-cyan-300"
                      : "text-zinc-500"
                }`}
              >
                <span
                  aria-hidden
                  className="h-2 w-2 rounded-full"
                  style={{
                    background: CONCEPT_COLOURS[concept] ?? OTHER_CONCEPT,
                  }}
                />
                {concept}
                {state === "done" ? ` ${found.get(concept)}` : ""}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
