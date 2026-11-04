"use client";

import type { ReactNode } from "react";

import type { Attempt, Check, Job } from "@/lib/api";
import type { HousingFact } from "@/lib/housingFacts";
import { type Stage, stageOf } from "@/lib/museStage";

import { BADGE, MARK, checkLabel } from "./AttemptRow";
import { HousingFacts } from "./HousingFacts";
import { Elapsed, Filmstrip, Steps, viewLabel, viewName } from "./MuseParts";
import { PrefabsMeanwhile } from "./PrefabsMeanwhile";

/** The run, large: about 90% of the screen, slightly see-through like the
 * site's build (BuildOverlay). On the stage, the one thing the run made
 * last, or the step it is on; beside it the steps, everything made so far,
 * the latest attempt's checks, and the prefabs to browse. */
export function MuseOverlay({
  job,
  names,
  facts,
  onHide,
}: {
  job: Job;
  names: ReadonlyMap<string, string>;
  facts: readonly HousingFact[];
  onHide: () => void;
}) {
  const stage = stageOf(job, names);
  const live = job.live;
  const checked = job.attempts.at(-1);
  return (
    <section
      aria-label="Muse at work"
      className="pointer-events-auto fixed inset-x-[5vw] inset-y-[5vh] z-40 flex flex-col gap-4 overflow-y-auto rounded-2xl bg-zinc-950/80 p-5 text-white shadow-2xl ring-1 ring-white/10 backdrop-blur lg:overflow-hidden"
    >
      <Header job={job} onHide={onHide} />
      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)]">
        <div className="flex min-h-0 flex-col gap-4">
          {scene(stage, { facts, onHide })}
          {factsUnder(job, stage) && <HousingFacts facts={facts} />}
        </div>
        <aside className="flex min-h-0 flex-col gap-5 overflow-y-auto pr-1">
          {live && <Steps phase={live.phase} detail={live.detail} />}
          <Filmstrip attempts={job.attempts} live={live} />
          {checked && <CheckList attempt={checked} />}
          <PrefabsMeanwhile />
        </aside>
      </div>
    </section>
  );
}

/** While Muse thinks over what is on the stage, the facts turn under it. */
function factsUnder(job: Job, stage: Stage): boolean {
  return (
    job.live?.phase === "thinking" &&
    (stage.kind === "view" || stage.kind === "fixing")
  );
}

function Header({ job, onHide }: { job: Job; onHide: () => void }) {
  const working = job.status === "queued" || job.status === "running";
  return (
    <header className="flex items-start justify-between gap-3">
      <p className="flex items-baseline gap-4">
        <span className="text-2xl font-semibold">Muse at work</span>
        {job.live && (
          <span className="text-zinc-300">Attempt {job.live.attempt}</span>
        )}
        {working && <Elapsed since={job.startedAt} />}
      </p>
      <button
        type="button"
        aria-label="Hide"
        onClick={onHide}
        className="-mt-1 -mr-1 rounded-full px-2.5 text-2xl leading-9 text-zinc-400 hover:bg-white/10 hover:text-white"
      >
        ×
      </button>
    </header>
  );
}

type Of<K extends Stage["kind"]> = Extract<Stage, { kind: K }>;

interface SceneProps {
  facts: readonly HousingFact[];
  onHide: () => void;
}

/** How each thing on the stage is drawn: what the run made last, full size,
 * or the step it is on. A new kind of Stage must be drawn here to compile. */
const SCENES: {
  [K in Stage["kind"]]: (stage: Of<K>, props: SceneProps) => ReactNode;
} = {
  waiting: (stage, { facts }) => (
    <Scene
      title={
        stage.queued
          ? "Waiting for a free designer…"
          : "Getting the site ready…"
      }
    >
      <HousingFacts facts={facts} large />
    </Scene>
  ),
  thinking: (_, { facts }) => (
    <Scene title="Muse decides its first move: a LiDAR view to ask for, or its design">
      <HousingFacts facts={facts} large />
    </Scene>
  ),
  reading: (stage) => (
    <Scene title={`Muse asked for ${viewName(stage.tool)}`}>
      <Working>Drawing it from the LiDAR…</Working>
    </Scene>
  ),
  view: (stage) => <ViewScene stage={stage} />,
  building: () => (
    <Scene title="Blender builds and renders it">
      <Working>Running Muse&apos;s script in Blender…</Working>
    </Scene>
  ),
  measuring: () => (
    <Scene title="The rules are measured">
      <Working>Measuring the design against the rules…</Working>
    </Scene>
  ),
  fixing: (stage) => (
    <Scene title={`Attempt ${stage.attempt.number} didn't pass`}>
      <Failure attempt={stage.attempt} />
      <p className="text-lg font-medium text-emerald-300 motion-safe:animate-pulse">
        Muse is fixing it…
      </p>
    </Scene>
  ),
  accepted: (stage, { onHide }) => (
    <AcceptedScene stage={stage} onHide={onHide} />
  ),
  stopped: (stage) => (
    <Scene title="Muse couldn't make a design that passes">
      {stage.error && <p className="text-zinc-300">{stage.error}</p>}
      {stage.attempt && <Failure attempt={stage.attempt} />}
    </Scene>
  ),
};

/** The scene for `stage`: its own drawing (TypeScript can't pair a union's
 * kind with its entry in SCENES unaided). */
function scene(stage: Stage, props: SceneProps): ReactNode {
  const draw = SCENES[stage.kind] as (
    stage: Stage,
    props: SceneProps,
  ) => ReactNode;
  return draw(stage, props);
}

function Scene({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <h2 aria-live="polite" className="text-xl font-medium">
        {title}
      </h2>
      {children}
    </div>
  );
}

/** A step under way that has made nothing yet: the stage waits, alive. */
function Working({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-48 flex-1 items-center justify-center rounded-xl bg-zinc-900/60 text-lg text-zinc-300 motion-safe:animate-pulse">
      {children}
    </div>
  );
}

/** An image from the run, as large as the stage allows. */
function Shown({ src, alt }: { src: string; alt: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- the API's own image
    <img
      src={src}
      alt={alt}
      className="build-fade-in min-h-48 w-full flex-1 rounded-xl bg-zinc-900/60 object-contain lg:min-h-0"
    />
  );
}

function ViewScene({ stage }: { stage: Extract<Stage, { kind: "view" }> }) {
  const named = stage.tool === null ? "" : `: ${viewName(stage.tool)}`;
  const label = viewLabel(stage.attempt, stage.number) + named;
  return (
    <Scene title={`${label}. Muse is reading it`}>
      <Shown key={stage.src} src={stage.src} alt={label} />
    </Scene>
  );
}

function AcceptedScene({
  stage,
  onHide,
}: {
  stage: Extract<Stage, { kind: "accepted" }>;
  onHide: () => void;
}) {
  const render = stage.attempt.files["design.png"];
  return (
    <Scene title={`Accepted: attempt ${stage.attempt.number}`}>
      {stage.visual ? (
        <>
          <Shown
            src={stage.visual}
            alt="AI illustration of the accepted design"
          />
          <p className="text-xs text-zinc-400">
            AI-illustrated by Muse Image; SAM 3.1 checked the house kept the
            design&apos;s shape. The surroundings are imagined.
          </p>
        </>
      ) : (
        render && (
          <Shown
            src={render}
            alt={`Attempt ${stage.attempt.number} as Blender rendered it`}
          />
        )
      )}
      <p className="flex items-center justify-between gap-3">
        <span className="text-zinc-300 motion-safe:animate-pulse">
          {stage.illustrating && "Muse Image is painting the visual…"}
        </span>
        <button
          type="button"
          onClick={onHide}
          className="rounded-full bg-emerald-400 px-4 py-1.5 text-sm font-medium text-zinc-950 hover:bg-emerald-300"
        >
          See it on your site
        </button>
      </p>
    </Scene>
  );
}

/** A failed attempt: its render, and what failed by how much (the
 * evaluator's measurements), or its words when there are no checks. */
function Failure({ attempt }: { attempt: Attempt }) {
  const render = attempt.files["design.png"];
  const failed = attempt.checks?.filter((c) => c.status === "fail") ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {render && (
        <Shown
          src={render}
          alt={`Attempt ${attempt.number} as Blender rendered it`}
        />
      )}
      {failed.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {failed.map((c) => (
            <li key={c.name} className="text-lg">
              <span className="font-medium text-red-300">
                ✗ {checkLabel(c.name)}:
              </span>{" "}
              {c.detail}
            </li>
          ))}
        </ul>
      ) : (
        <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap text-sm text-zinc-300">
          {attempt.feedback}
        </pre>
      )}
    </div>
  );
}

/** A check's verdict in words, for a screen reader (the mark is drawn). */
const SAID: Record<Check["status"], string> = {
  pass: "Passed",
  fail: "Failed",
  unknown: "Undecided",
};

/** An attempt's checks as a checklist: each verdict, and what was measured. */
function CheckList({ attempt }: { attempt: Attempt }) {
  if (!attempt.checks?.length) return null;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-300">
        Attempt {attempt.number}&apos;s checks
      </h3>
      <ul
        aria-label={`Attempt ${attempt.number}'s checks`}
        className="flex flex-col gap-1.5 text-sm"
      >
        {attempt.checks.map((c) => (
          <li key={c.name} className="flex gap-2">
            <span
              aria-hidden
              className={`h-5 w-5 shrink-0 rounded-md text-center text-xs leading-5 ring-1 ${BADGE[c.status]}`}
            >
              {MARK[c.status]}
            </span>
            <span className="min-w-0">
              <span className="sr-only">{SAID[c.status]}: </span>
              <span className="font-medium">{checkLabel(c.name)}</span>
              <span className="block text-xs text-zinc-400">{c.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
