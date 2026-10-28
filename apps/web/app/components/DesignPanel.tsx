"use client";

import { Component, type ReactNode, useState } from "react";

import type { Attempt, Job } from "@/lib/api";

import { ModelViewer } from "./ModelViewer";
import { BeforeAfter, DesignHistory, RevisionForm } from "./Revisions";
import { useDesignChain } from "./useDesignChain";
import { VERDICT_STYLE } from "./verdicts";

/** Brief the design agent, then follow its attempts as the independent
 * evaluator checks each one, ending with the accepted concept in 3D. An
 * accepted design can be changed in plain words, as often as wanted: the
 * history lists each change and shows any step beside the one it changed. */
export function DesignPanel({ pollMs = 2000 }: { pollMs?: number }) {
  const { chain, shown, select, problem, busy, design, revise } =
    useDesignChain(pollMs);
  const parent = shown && chain.find((j) => j.id === shown.parentId);
  return (
    <section className="flex flex-col gap-4">
      <BriefForm busy={busy} onSubmit={design} />
      {problem && <p className="text-red-700">{problem}</p>}
      {shown && chain.length > 1 && (
        <DesignHistory chain={chain} shown={shown} onSelect={select} />
      )}
      {shown && (
        <DesignView
          key={shown.id}
          job={shown}
          parent={parent}
          busy={busy}
          onRevise={(instruction) => revise(shown, instruction)}
        />
      )}
    </section>
  );
}

/** One design of the chain: its status, its attempts, the one on show in 3D
 * and, once a design is accepted, a way to change it. A revision is shown
 * beside the accepted design it changed. */
function DesignView({
  job,
  parent,
  busy,
  onRevise,
}: {
  job: Job;
  parent: Job | undefined;
  busy: boolean;
  onRevise: (instruction: string) => void;
}) {
  const [viewing, setViewing] = useState<number | null>(null);
  const model = modelUrl(job, viewing ?? job.acceptedAttempt);
  return (
    <>
      <JobStatus job={job} />
      {parent && <BeforeAfter before={parent} after={job} />}
      {job.attempts.map((attempt) => (
        <AttemptCard
          key={attempt.number}
          attempt={attempt}
          onView={setViewing}
        />
      ))}
      {model && (
        <ViewerBoundary key={model}>
          <ModelViewer url={model} />
        </ViewerBoundary>
      )}
      {job.status === "done" && job.acceptedAttempt !== null && (
        <RevisionForm busy={busy} onSubmit={onRevise} />
      )}
    </>
  );
}

/** The 3D model of attempt ``number``, if it has one. */
function modelUrl(job: Job, number: number | null): string | undefined {
  return job.attempts.find((a) => a.number === number)?.files["design.glb"];
}

function BriefForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (brief: string, observe: boolean) => void;
}) {
  const [brief, setBrief] = useState("");
  const [observe, setObserve] = useState(true);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(brief, observe);
      }}
      className="flex flex-col gap-2"
    >
      <label htmlFor="brief" className="font-medium">
        Brief
      </label>
      <textarea
        id="brief"
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        rows={3}
        maxLength={4000}
        className="rounded border border-zinc-300 p-2 dark:border-zinc-700 dark:bg-zinc-900"
        placeholder="A small one-bedroom prefab that keeps the garden and trees."
      />
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={observe}
          onChange={(e) => setObserve(e.target.checked)}
        />
        Let the model request LiDAR views
      </label>
      <button
        type="submit"
        disabled={!brief.trim() || busy}
        className="self-start rounded bg-zinc-900 px-4 py-2 text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
      >
        Design
      </button>
    </form>
  );
}

/** The shown job's status line (role "status", so it is announced as it
 * changes, and can be told apart from attempt feedback). */
function JobStatus({ job }: { job: Job }) {
  if (job.status === "failed") {
    return (
      <p role="status" className="text-red-700">
        The design run failed: {job.error}
      </p>
    );
  }
  if (job.status === "done") {
    return (
      <p role="status" className="font-medium">
        {job.acceptedAttempt === null
          ? "No attempt passed every check."
          : `Accepted: attempt ${job.acceptedAttempt}`}
      </p>
    );
  }
  return (
    <p role="status" className="text-zinc-600">
      Design {job.status}…
    </p>
  );
}

function AttemptCard({
  attempt,
  onView,
}: {
  attempt: Attempt;
  onView: (n: number) => void;
}) {
  const image = attempt.files["design.png"];
  const visual = attempt.files["visual.png"]; // only if it kept the design's shape
  return (
    <article className="flex flex-col gap-2 rounded border border-zinc-200 p-3 dark:border-zinc-800">
      <header className="flex items-center gap-2">
        <h3 className="font-medium">Attempt {attempt.number}</h3>
        <span
          className={`rounded px-2 text-sm ${VERDICT_STYLE[attempt.status]}`}
        >
          {attempt.status}
        </span>
        {attempt.files["design.glb"] && (
          <button
            type="button"
            onClick={() => onView(attempt.number)}
            className="ml-auto text-sm underline"
          >
            View in 3D
          </button>
        )}
      </header>
      {attempt.observations.length > 0 && (
        <ul className="flex flex-wrap gap-1 text-xs">
          {attempt.observations.map((tool, i) => (
            <li key={i} className="rounded bg-sky-100 px-2 text-sky-900">
              {tool}
            </li>
          ))}
        </ul>
      )}
      <pre className="whitespace-pre-wrap text-sm">{attempt.feedback}</pre>
      {image && (
        // eslint-disable-next-line @next/next/no-img-element -- a render served by the API
        <img
          src={image}
          alt={`Attempt ${attempt.number} render`}
          className="max-w-md rounded"
        />
      )}
      {visual && <Illustration src={visual} number={attempt.number} />}
    </article>
  );
}

/** Muse Image's picture of the design, shown only when the building in it
 * still matched the checked design's silhouette. Everything else in it is
 * imagined, and the caption says so. */
function Illustration({ src, number }: { src: string; number: number }) {
  return (
    <figure className="flex max-w-md flex-col gap-1">
      {/* eslint-disable-next-line @next/next/no-img-element -- an image served by the API */}
      <img
        src={src}
        alt={`AI illustration of attempt ${number}`}
        className="rounded"
      />
      <figcaption className="text-xs text-zinc-600 dark:text-zinc-400">
        AI-illustrated by Muse Image from the checked design. Only the new
        dwelling&apos;s position and shape were checked against it; the
        surroundings are imagined, not the real site.
      </figcaption>
    </figure>
  );
}

/** A model that can't load (a failed request, no WebGL) replaces only the
 * viewer with its reason: the run's results stay on the page. */
class ViewerBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <p className="text-red-700">
          Could not show the 3D model: {this.state.error.message}
        </p>
      );
    }
    return this.props.children;
  }
}
