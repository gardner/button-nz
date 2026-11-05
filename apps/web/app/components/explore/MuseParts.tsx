"use client";

import type { Attempt, Live, Phase, Placement } from "@/lib/api";
import { fitsWords } from "@/lib/massing";
import { viewNumber } from "@/lib/museStage";

import { useNow } from "./useTurn";

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
export const VIEWS: Record<string, string> = {
  render_hillshade: "the shaded relief",
  render_contours: "the contours",
  render_height_map: "a height map",
  render_cross_section: "a cross-section",
  inspect_elevation: "exact ground heights",
};

/** A view's tool in words: as VIEWS says, else its own name. */
export function viewName(tool: string): string {
  return VIEWS[tool] ?? tool.replaceAll("_", " ");
}

export const VERDICTS: Record<Attempt["status"], string> = {
  pass: "passed",
  unknown: "passed, with checks it couldn't decide",
  fail: "failed a check",
  error: "didn't run",
};

export function Steps({ phase, detail }: { phase: Phase; detail: string }) {
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
              className={`h-2 w-2 rounded-full ${now ? "bg-emerald-400 motion-safe:animate-ping" : "bg-zinc-600"}`}
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

/** A LiDAR view's name: its number as its attempt numbers it
 * (observation-<n>.png), the same on the stage and in the filmstrip. */
export function viewLabel(attempt: number, number: number): string {
  return `LiDAR view ${number} of attempt ${attempt}`;
}

/** The run so far, oldest first: each finished attempt's LiDAR views and
 * its render with its verdict, then the views of the attempt under way. */
export function Filmstrip({
  attempts,
  live,
}: {
  attempts: Attempt[];
  live: Live | null;
}) {
  const frames = [
    ...attempts.flatMap(framesOf),
    ...(live?.observations.map((src) => viewFrame(live.attempt, src)) ?? []),
  ];
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

function viewFrame(attempt: number, src: string): Frame {
  return { src, alt: viewLabel(attempt, viewNumber(src)) };
}

/** A finished attempt's views, in the order made, then its render. */
function framesOf(attempt: Attempt): Frame[] {
  const views = Object.keys(attempt.files)
    .filter((name) => name.startsWith("observation-"))
    .map((name) => attempt.files[name])
    .sort((a, b) => viewNumber(a) - viewNumber(b))
    .map((src) => viewFrame(attempt.number, src));
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

/** Minutes and seconds since `since` (the run's start, say), ticking; small
 * and grey, or `plain` in the words around it. */
export function Elapsed({
  since,
  plain = false,
}: {
  since: string | null;
  plain?: boolean;
}) {
  const now = useNow(1000);
  if (since === null) return null;
  const seconds = Math.max(0, Math.floor((now - Date.parse(since)) / 1000));
  const shown = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return (
    <span
      className={
        plain ? "tabular-nums" : "font-mono text-sm tabular-nums text-zinc-400"
      }
    >
      {shown}
    </span>
  );
}

/** Where a home of the run's plan fits, checked, as the run's first item:
 * known in seconds, long before Muse has said anything (#188). */
export function Fits({ placement }: { placement: Placement }) {
  return (
    <p className="rounded-xl bg-emerald-400/10 px-3 py-2 text-sm text-emerald-100 ring-1 ring-emerald-400/30">
      {fitsWords(placement)}
    </p>
  );
}
