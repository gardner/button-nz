"use client";

import { useState } from "react";

import type { Attempt, Check } from "@/lib/api";

const LABELS: Record<string, string> = {
  product_footprint: "The prefab's footprint",
  within_site: "On the title",
  title_boundary_setback: "2 m from the boundary",
  section_boundary_setback: "Section lines",
  building_separation: "2 m from buildings",
  floor_area: "70 m² or less",
  single_storey: "One storey",
  height: "4 m high or less",
  floor_level: "Floor 1 m up or less",
  preservation_areas: "Keep-clear areas",
};

/** A check's name in plain words. */
export function checkLabel(name: string): string {
  return LABELS[name] ?? name.replaceAll("_", " ");
}

const MARK: Record<Check["status"], string> = {
  pass: "✓",
  fail: "✗",
  unknown: "?",
};
const BADGE: Record<Check["status"], string> = {
  pass: "bg-emerald-500/20 text-emerald-300 ring-emerald-400/40",
  fail: "bg-red-500/20 text-red-300 ring-red-400/40",
  unknown: "bg-amber-400/15 text-amber-200 ring-amber-300/40",
};
const VERDICT: Record<Attempt["status"], string> = {
  pass: "bg-emerald-500 text-zinc-950",
  unknown: "bg-emerald-500/70 text-zinc-950",
  fail: "bg-red-500 text-white",
  error: "bg-zinc-600 text-white",
};
const VERDICT_WORD: Record<Attempt["status"], string> = {
  pass: "Passed",
  unknown: "Passed, some unknown",
  fail: "Failed",
  error: "Didn't build",
};

/** One attempt: its render, its verdict, a badge per check, and, opened,
 * each check's measurement and rule (or the evaluator's words, when the API
 * sends no checks). */
export function AttemptRow({ attempt }: { attempt: Attempt }) {
  const [open, setOpen] = useState(false);
  const render = attempt.files["design.png"];
  return (
    <article className="flex flex-col gap-2 rounded-xl bg-white/5 p-3">
      <div className="flex items-start gap-3">
        {render ? (
          // eslint-disable-next-line @next/next/no-img-element -- a render served by the API
          <img
            src={render}
            alt={`Attempt ${attempt.number} render`}
            className="h-16 w-24 shrink-0 rounded-lg object-cover"
          />
        ) : (
          <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded-lg bg-white/5 text-xs text-zinc-500">
            no render
          </div>
        )}
        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="flex items-center gap-2 text-sm">
            <span className="font-semibold">Attempt {attempt.number}</span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT[attempt.status]}`}
            >
              {VERDICT_WORD[attempt.status]}
            </span>
          </p>
          {attempt.checks && (
            <ul aria-label="Checks" className="flex flex-wrap gap-1">
              {attempt.checks.map((c) => (
                <li
                  key={c.name}
                  className={`rounded-md px-1.5 py-0.5 text-xs ring-1 ${BADGE[c.status]}`}
                >
                  {MARK[c.status]} {checkLabel(c.name)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="self-start text-xs text-zinc-400 underline-offset-2 hover:underline"
      >
        {open ? "Hide details" : "Details"}
      </button>
      {open &&
        (attempt.checks ? (
          <dl className="flex flex-col gap-1.5 text-xs">
            {attempt.checks.map((c) => (
              <div key={c.name}>
                <dt className="font-medium">
                  {MARK[c.status]} {checkLabel(c.name)}
                </dt>
                <dd className="text-zinc-300">{c.detail}</dd>
                <dd className="text-zinc-500">{c.rule}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <pre className="whitespace-pre-wrap text-xs text-zinc-300">
            {attempt.feedback}
          </pre>
        ))}
    </article>
  );
}
