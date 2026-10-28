"use client";

import { Component, type ReactNode, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type Attempt,
  type Job,
  createDesign,
  getDesign,
} from "@/lib/api";

import { ModelViewer } from "./ModelViewer";

const VERDICT_STYLE: Record<Attempt["status"], string> = {
  pass: "bg-green-100 text-green-900",
  unknown: "bg-amber-100 text-amber-900",
  fail: "bg-red-100 text-red-900",
  error: "bg-zinc-200 text-zinc-900",
};

/** Brief the design agent, then follow its attempts as the independent
 * evaluator checks each one, ending with the accepted concept in 3D. */
export function DesignPanel({ pollMs = 2000 }: { pollMs?: number }) {
  const { job, problem, busy, start } = useDesignJob(pollMs);
  const [viewing, setViewing] = useState<number | null>(null);
  const model = job && modelUrl(job, viewing ?? job.acceptedAttempt);
  return (
    <section className="flex flex-col gap-4">
      <BriefForm
        busy={busy}
        onSubmit={(brief, observe) => {
          setViewing(null);
          start(brief, observe);
        }}
      />
      {problem && <p className="text-red-700">{problem}</p>}
      {job && <JobStatus job={job} />}
      {job?.attempts.map((attempt) => (
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
    </section>
  );
}

/** The 3D model of attempt ``number``, if it has one. */
function modelUrl(job: Job, number: number | null): string | undefined {
  return job.attempts.find((a) => a.number === number)?.files["design.glb"];
}

/** A design job: started on request, then polled until it is done or failed.
 * A transient poll failure is shown and retried; a permanent one (the API no
 * longer has the job) stops polling. One design is started at a time. */
function useDesignJob(pollMs: number) {
  const [job, setJob] = useState<Job | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const starting = useRef(false); // guards clicks before the re-render disables Design
  const [lost, setLost] = useState(false); // the API can't give this job any more
  const active =
    !lost && (job?.status === "queued" || job?.status === "running");
  useEffect(() => {
    if (!active || job === null) return;
    const timer = setTimeout(() => {
      getDesign(job.id).then(
        (next) => {
          setProblem(null);
          setJob(next);
        },
        (e: Error) => {
          setProblem(e.message);
          if (e instanceof ApiError && !e.transient) setLost(true);
          else setRetries((n) => n + 1);
        },
      );
    }, pollMs);
    return () => clearTimeout(timer);
  }, [active, job, pollMs, retries]);

  function start(brief: string, observe: boolean) {
    if (starting.current) return;
    starting.current = true;
    setSubmitting(true);
    setProblem(null);
    setJob(null); // stop following the old job before the new one exists
    setLost(false);
    createDesign(brief, observe)
      .then(setJob, (e: Error) => setProblem(e.message))
      .finally(() => {
        starting.current = false;
        setSubmitting(false);
      });
  }
  return { job, problem, busy: submitting || active, start };
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

function JobStatus({ job }: { job: Job }) {
  if (job.status === "failed") {
    return <p className="text-red-700">The design run failed: {job.error}</p>;
  }
  if (job.status === "done") {
    return (
      <p className="font-medium">
        {job.acceptedAttempt === null
          ? "No attempt passed every check."
          : `Accepted: attempt ${job.acceptedAttempt}`}
      </p>
    );
  }
  return <p className="text-zinc-600">Design {job.status}…</p>;
}

function AttemptCard({
  attempt,
  onView,
}: {
  attempt: Attempt;
  onView: (n: number) => void;
}) {
  const image = attempt.files["design.png"];
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
    </article>
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
