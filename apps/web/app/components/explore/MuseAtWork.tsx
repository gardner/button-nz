"use client";

import { useEffect, useState } from "react";

import type { Attempt, Job, Phase } from "@/lib/api";

/** The steps of one attempt, in the order a run takes them (Muse decides,
 * then reads a view or has its script built, as many times as it asks). */
const STEPS: { phase: Phase; label: string }[] = [
  // Every model call: Muse choosing a LiDAR view to ask for, or writing its
  // Blender script. The run can't tell which until Muse answers.
  { phase: "thinking", label: "Muse decides its next move" },
  { phase: "observing", label: "Muse reads the LiDAR" },
  { phase: "rendering", label: "Blender builds and renders it" },
  { phase: "checking", label: "The rules are measured" },
];

/** The LiDAR views Muse can ask for, in words. */
const VIEWS: Record<string, string> = {
  render_hillshade: "the shaded relief",
  render_contours: "the contours",
  render_height_map: "a height map",
  render_cross_section: "a cross-section",
  inspect_elevation: "exact ground heights",
};

const VERDICTS: Record<Attempt["status"], string> = {
  pass: "passed",
  unknown: "passed, with checks it couldn't decide",
  fail: "failed a check",
  error: "didn't run",
};

/** While a design runs, the run itself: the step it is on, lit, and a
 * filmstrip of what it has made so far, every image real (the LiDAR views
 * Muse asked for, each attempt's render with its verdict). */
export function MuseAtWork({ job }: { job: Job }) {
  const live = job.live;
  return (
    <section
      aria-label="Muse at work"
      className="flex flex-col gap-3 rounded-2xl bg-zinc-950/90 p-4 text-white shadow-2xl backdrop-blur"
    >
      <header className="flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Muse at work</h2>
        <Elapsed since={job.startedAt} />
      </header>
      {live ? (
        <>
          <p className="text-sm text-zinc-300">Attempt {live.attempt}</p>
          <Steps phase={live.phase} detail={live.detail} />
        </>
      ) : (
        <p className="animate-pulse text-sm text-emerald-300">
          {job.status === "queued"
            ? "Waiting for a free designer…"
            : "Getting the site ready…"}
        </p>
      )}
      <Filmstrip attempts={job.attempts} views={live?.observations ?? []} />
    </section>
  );
}

function Steps({ phase, detail }: { phase: Phase; detail: string }) {
  return (
    <ol className="flex flex-col gap-1.5 text-sm">
      {STEPS.map((step) => {
        const now = step.phase === phase;
        return (
          <li
            key={step.phase}
            aria-current={now ? "step" : undefined}
            className={`flex items-center gap-2 ${now ? "font-medium text-emerald-300" : "text-zinc-500"}`}
          >
            <span
              aria-hidden
              className={`h-2 w-2 rounded-full ${now ? "animate-ping bg-emerald-400" : "bg-zinc-600"}`}
            />
            {step.label}
            {now && phase === "observing" && VIEWS[detail] && (
              <span className="text-zinc-300">: {VIEWS[detail]}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** The run so far, oldest first: each finished attempt's LiDAR views and
 * its render with its verdict, then the views of the attempt under way. */
function Filmstrip({
  attempts,
  views,
}: {
  attempts: Attempt[];
  views: string[];
}) {
  const frames = numbered([
    ...attempts.flatMap(framesOf),
    ...views.map((src) => ({ src, alt: "" })),
  ]);
  if (frames.length === 0) return null;
  return (
    <ul className="flex gap-2 overflow-x-auto pb-1">
      {frames.map((frame) => (
        <li key={frame.src} className="relative shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element -- the API's own image */}
          <img
            src={frame.src}
            alt={frame.alt}
            className={`h-24 rounded-lg object-cover ${frame.badge ? "w-32" : "w-24"}`}
          />
          {frame.badge && (
            <span
              aria-hidden
              className={`absolute right-1 top-1 rounded-full px-1.5 text-xs font-bold ${frame.badge === "✗" ? "bg-red-500" : "bg-emerald-500"}`}
            >
              {frame.badge}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

interface Frame {
  src: string;
  alt: string;
  badge?: "✓" | "✗"; // a render's verdict
}

/** The views (frames with no verdict) named in the order they were made. */
function numbered(frames: Frame[]): Frame[] {
  let views = 0;
  return frames.map((f) =>
    f.badge ? f : { ...f, alt: `LiDAR view ${++views} Muse asked for` },
  );
}

/** A finished attempt's views, in the order made, then its render. */
function framesOf(attempt: Attempt): Frame[] {
  const views = Object.keys(attempt.files)
    .filter((name) => name.startsWith("observation-"))
    .sort((a, b) => viewNumber(a) - viewNumber(b))
    .map((name): Frame => ({ src: attempt.files[name], alt: "" }));
  const render = attempt.files["design.png"];
  if (!render) return views;
  const failed = attempt.status === "fail" || attempt.status === "error";
  return [
    ...views,
    {
      src: render,
      alt: `Attempt ${attempt.number}'s render: ${VERDICTS[attempt.status]}`,
      badge: failed ? "✗" : "✓",
    },
  ];
}

function viewNumber(name: string): number {
  return Number(name.slice("observation-".length, -".png".length));
}

/** Minutes and seconds since the run started, ticking. */
function Elapsed({ since }: { since: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (since === null) return null;
  const seconds = Math.max(0, Math.floor((now - Date.parse(since)) / 1000));
  const shown = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <span className="font-mono text-sm tabular-nums text-zinc-400">
      {shown}
    </span>
  );
}
