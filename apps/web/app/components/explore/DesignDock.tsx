"use client";

import { useState } from "react";

import type { Job } from "@/lib/api";

import { DesignHistory, RevisionForm } from "../Revisions";
import type { useDesignChain } from "../useDesignChain";
import { AttemptRow } from "./AttemptRow";

export const EXAMPLES = [
  "A one-bedroom studio that gets the afternoon sun",
  "A two-bedroom flat for Mum, keeping the trees",
  "A compact studio as far from the street as the rules allow",
];

type Chain = ReturnType<typeof useDesignChain>;

/** The brief (with examples to start from), the design on show as it is
 * made and checked, its history, and a box to change it in plain words. */
export function DesignDock({ chain }: { chain: Chain }) {
  const { shown, busy, problem } = chain;
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-zinc-950/85 p-5 shadow-2xl backdrop-blur">
      <BriefBox busy={busy} onDesign={(brief) => chain.design(brief, true)} />
      {problem && (
        <p role="alert" className="text-sm text-red-300">
          {problem}
        </p>
      )}
      {shown && chain.chain.length > 1 && (
        <DesignHistory
          chain={chain.chain}
          shown={shown}
          onSelect={chain.select}
        />
      )}
      {shown && (
        <Shown
          job={shown}
          busy={busy}
          onRevise={(i) => chain.revise(shown, i)}
        />
      )}
    </section>
  );
}

function BriefBox({
  busy,
  onDesign,
}: {
  busy: boolean;
  onDesign: (brief: string) => void;
}) {
  const [brief, setBrief] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onDesign(brief);
      }}
      className="flex flex-col gap-2"
    >
      <label htmlFor="brief" className="text-lg font-semibold">
        What would you like to build?
      </label>
      <textarea
        id="brief"
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        rows={2}
        maxLength={4000}
        placeholder="In your own words…"
        className="rounded-xl bg-white px-3 py-2 text-zinc-900 outline-none focus:ring-4 focus:ring-emerald-400/60"
      />
      <ul aria-label="Examples" className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <li key={example}>
            <button
              type="button"
              onClick={() => setBrief(example)}
              className="rounded-full bg-white/10 px-2.5 py-1 text-xs hover:bg-white/20"
            >
              {example}
            </button>
          </li>
        ))}
      </ul>
      <button
        type="submit"
        disabled={!brief.trim() || busy}
        className="self-start rounded-xl bg-emerald-400 px-5 py-2 font-semibold text-zinc-950 shadow-lg disabled:opacity-40"
      >
        Design it
      </button>
    </form>
  );
}

function Shown({
  job,
  busy,
  onRevise,
}: {
  job: Job;
  busy: boolean;
  onRevise: (instruction: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Status job={job} />
      {job.attempts.map((a) => (
        <AttemptRow key={a.number} attempt={a} />
      ))}
      {job.status === "done" && job.acceptedAttempt !== null && (
        <div className="rounded-xl bg-white p-3 text-zinc-900">
          <RevisionForm busy={busy} onSubmit={onRevise} />
        </div>
      )}
    </div>
  );
}

/** The shown design's state, announced as it changes. */
function Status({ job }: { job: Job }) {
  const [text, tone] =
    job.status === "failed"
      ? [
          `The design run failed: ${job.error ?? "no reason given"}`,
          "text-red-300",
        ]
      : job.status !== "done"
        ? [
            job.status === "queued"
              ? "Queued…"
              : "Muse is designing: reading the LiDAR, writing Blender, checking…",
            "text-emerald-300 animate-pulse",
          ]
        : job.acceptedAttempt === null
          ? ["No attempt passed every check.", "text-amber-200"]
          : [`Accepted: attempt ${job.acceptedAttempt}`, "text-emerald-300"];
  return (
    <p role="status" className={`text-sm font-medium ${tone}`}>
      {text}
    </p>
  );
}
