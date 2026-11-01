"use client";

import { Component, type ReactNode, useState } from "react";

import type { Job } from "@/lib/api";

import { ModelViewer } from "../ModelViewer";
import { BeforeAfter } from "../Revisions";

/** The hero panel's width, in pixels: the map keeps it clear. */
export const HERO_WIDTH = 400;

type Tab = "model" | "visual" | "compare";

/** The accepted design, big: in 3D on the site's terrain, as Muse Image
 * illustrated it (shown only when it kept the design's shape), and beside
 * the design it revised. */
export function HeroMedia({
  job,
  parent,
}: {
  job: Job;
  parent: Job | undefined;
}) {
  const { model, visual, tabs } = mediaOf(job, parent);
  const available = tabs.filter((t) => t.on);
  const [chosen, setChosen] = useState<Tab | null>(null);
  const tab = available.find((t) => t.key === chosen)?.key ?? available[0]?.key;
  if (!tab) return null;
  return (
    <section
      aria-label="The accepted design"
      className="flex w-[min(400px,calc(100vw-2rem))] flex-col gap-2 rounded-2xl bg-zinc-950/85 p-3 shadow-2xl backdrop-blur"
    >
      <div role="tablist" className="flex gap-1">
        {available.map((t) => (
          <button
            key={t.key}
            role="tab"
            type="button"
            aria-selected={t.key === tab}
            onClick={() => setChosen(t.key)}
            className={`rounded-lg px-3 py-1 text-sm ${
              t.key === tab
                ? "bg-white text-zinc-950"
                : "text-zinc-300 hover:bg-white/10"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <TabBody
        tab={tab}
        model={model}
        visual={visual}
        job={job}
        parent={parent}
      />
    </section>
  );
}

function TabBody({
  tab,
  model,
  visual,
  job,
  parent,
}: {
  tab: Tab;
  model: string | undefined;
  visual: string | undefined;
  job: Job;
  parent: Job | undefined;
}) {
  if (tab === "model" && model)
    return (
      <Contained key={model}>
        <ModelViewer url={model} height="h-[300px]" />
      </Contained>
    );
  if (tab === "visual" && visual)
    return (
      <figure className="flex flex-col gap-1">
        {/* eslint-disable-next-line @next/next/no-img-element -- an image served by the API */}
        <img
          src={visual}
          alt="AI illustration of the accepted design"
          className="rounded-xl"
        />
        <figcaption className="text-xs text-zinc-400">
          AI-illustrated by Muse Image; SAM 3.1 checked the house kept the
          design&apos;s shape. The surroundings are imagined.
        </figcaption>
      </figure>
    );
  if (tab === "compare" && parent)
    return (
      <div className="rounded-xl bg-white p-2 text-zinc-900">
        <BeforeAfter before={parent} after={job} />
      </div>
    );
  return null;
}

function mediaOf(job: Job, parent: Job | undefined) {
  const accepted = job.attempts.find((a) => a.number === job.acceptedAttempt);
  const model = accepted?.files["design.glb"];
  const visual = accepted?.files["visual.png"];
  const tabs: { key: Tab; label: string; on: boolean }[] = [
    { key: "model", label: "3D", on: Boolean(model) },
    { key: "visual", label: "AI visual", on: Boolean(visual) },
    { key: "compare", label: "Before / after", on: Boolean(parent) },
  ];
  return { model, visual, tabs };
}

/** A model that can't load (no WebGL, a failed request) shows why instead. */
class Contained extends Component<
  { children: ReactNode },
  { error: string | null }
> {
  state = { error: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }

  render() {
    return this.state.error ? (
      <p className="p-4 text-sm text-red-300">
        The 3D model couldn&apos;t show: {this.state.error}
      </p>
    ) : (
      this.props.children
    );
  }
}
