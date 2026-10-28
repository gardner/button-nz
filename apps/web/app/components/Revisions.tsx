"use client";

import { useState } from "react";

import type { Attempt, Job } from "@/lib/api";

import { acceptedAttempt, jobVerdict } from "./verdicts";

/** Ask for a change to the design on show, in plain words. */
export function RevisionForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (instruction: string) => void;
}) {
  const [instruction, setInstruction] = useState("");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(instruction);
      }}
      className="flex flex-col gap-2"
    >
      <label htmlFor="instruction" className="font-medium">
        Change this design
      </label>
      <textarea
        id="instruction"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        rows={2}
        maxLength={2000}
        className="rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-900"
        placeholder="Move it 3 m further from the street."
      />
      <button
        type="submit"
        disabled={!instruction.trim() || busy}
        className="self-start rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
      >
        Revise
      </button>
    </form>
  );
}

/** The chain so far: the original brief, then each change in the order it
 * was asked for, with its verdict. Selecting a step shows that design. */
export function DesignHistory({
  chain,
  shown,
  onSelect,
}: {
  chain: Job[];
  shown: Job;
  onSelect: (id: string) => void;
}) {
  return (
    <ol aria-label="Design history" className="flex flex-col gap-1">
      {chain.map((job, i) => {
        const verdict = jobVerdict(job);
        return (
          <li key={job.id}>
            <button
              type="button"
              aria-current={job === shown ? "step" : undefined}
              onClick={() => onSelect(job.id)}
              className="flex w-full items-center gap-2 rounded border border-zinc-200 px-2 py-1 text-left aria-[current=step]:border-zinc-900 dark:border-zinc-800 dark:aria-[current=step]:border-zinc-100"
            >
              <span className="text-zinc-600">{i + 1}.</span>
              <span className="flex-1 truncate">{stepLabel(chain, i)}</span>
              <span className={`rounded px-2 text-sm ${verdict.style}`}>
                {verdict.label}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** What step `i` asked for. A change to a step other than the one before it
 * (after a failed revision, say) names the step it changed. */
function stepLabel(chain: Job[], i: number): string {
  const job = chain[i];
  if (job.instruction === null) return `Original brief: ${job.brief}`;
  const parent = chain.findIndex((j) => j.id === job.parentId);
  return parent === i - 1
    ? job.instruction
    : `Change to step ${parent + 1}: ${job.instruction}`;
}

/** A revision's accepted render beside the one it changed. */
export function BeforeAfter({ before, after }: { before: Job; after: Job }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <AcceptedRender job={before} caption="Before" />
      <AcceptedRender job={after} caption="After" />
    </div>
  );
}

function AcceptedRender({ job, caption }: { job: Job; caption: string }) {
  const accepted = acceptedAttempt(job);
  const image = accepted?.files["design.png"];
  return (
    <figure className="flex flex-col gap-1">
      {accepted && image ? (
        // eslint-disable-next-line @next/next/no-img-element -- a render served by the API
        <img
          src={image}
          alt={`${caption}: attempt ${accepted.number} render`}
          className="w-full rounded"
        />
      ) : (
        <p className="text-sm text-zinc-600">{noRender(job, accepted)}</p>
      )}
      <figcaption className="text-sm font-medium">{caption}</figcaption>
    </figure>
  );
}

function noRender(job: Job, accepted: Attempt | undefined): string {
  if (accepted) return "The accepted attempt has no render.";
  if (job.status === "done" || job.status === "failed") {
    return "Nothing was accepted.";
  }
  return "Not ready yet.";
}
