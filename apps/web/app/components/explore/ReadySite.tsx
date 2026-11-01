"use client";

import { useEffect, useState } from "react";

import type { Job } from "@/lib/api";
import { type Bounds, boundsOf } from "@/lib/geo";
import type { DesignMap, SiteMap } from "@/lib/siteMap";
import type { SiteState } from "@/lib/sites";

import { useDesignChain } from "../useDesignChain";
import { useSurvey } from "../useSurvey";
import { FitTo } from "../map/FitTo";
import { DesignDock } from "./DesignDock";
import { DistanceLabels } from "./DistanceLabels";
import { HERO_WIDTH, HeroMedia } from "./HeroMedia";
import { PrefabSection } from "./PrefabSection";
import { SurveyPanel } from "./SurveyPanel";
import { DesignLayers, SiteLayers } from "./SiteLayers";
import type { JourneyState } from "./Stepper";
import { useDesignMap, useSiteMap } from "./useMapLayers";

/** How far the journey has got past finding the site, for the stepper. */
export type Progress = Omit<JourneyState, "site">;

/** A site that is ready: the rules drawn on it, its survey to decide, the
 * design dock, and the accepted design on the map and as a hero. It tells
 * the page how far the design has got, for the stepper. */
export function ReadySite({
  site,
  pollMs,
  onProgress,
}: {
  site: SiteState;
  pollMs: number;
  onProgress: (progress: Progress) => void;
}) {
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false); // the survey, opened again
  const chain = useDesignChain(pollMs, site.id);
  const [checkedBefore, setCheckedBefore] = useState<readonly string[]>([]);
  const survey = useSurvey(site.id, () => {
    setVersion((v) => v + 1);
    // Every design so far was checked on the survey as it was.
    setCheckedBefore(chain.chain.map((j) => j.id));
  });
  const siteMap = useSiteMap(site.id, version);
  const shown = chain.shown;
  const designMap = useDesignMap(shown);
  const accepted = shown?.status === "done" && shown.acceptedAttempt !== null;
  const outdated = shown !== undefined && checkedBefore.includes(shown.id);

  const askedPrefabs = useProgress(shown, onProgress);

  return (
    <>
      <SiteOverlays
        siteMap={siteMap.map}
        designMap={accepted ? designMap.map : null}
        selected={selected}
        onFeature={(id) => {
          setSelected(id);
          setEditing(true);
        }}
      />
      <SiteHeader
        address={site.address}
        problems={problemsOf(siteMap.problem, designMap.problem, outdated)}
      />
      <SurveyPanel
        control={survey}
        selected={selected}
        onSelect={setSelected}
        compact={Boolean(shown) && !editing}
        onEdit={() => setEditing(true)}
      />
      <DesignDock chain={chain} />
      {accepted && shown && (
        <Accepted job={shown} chain={chain} onAsked={askedPrefabs} />
      )}
    </>
  );
}

/** What a ready site draws on the map: its rules and survey, and the
 * accepted design with its distances. */
function SiteOverlays({
  siteMap,
  designMap,
  selected,
  onFeature,
}: {
  siteMap: SiteMap | null;
  designMap: DesignMap | null;
  selected: string | null;
  onFeature: (id: string) => void;
}) {
  return (
    <>
      {siteMap && (
        <SiteLayers
          map={siteMap}
          selected={selected}
          onFeature={(f) => onFeature(f.id)}
        />
      )}
      {designMap && (
        <>
          <DesignLayers map={designMap} />
          <DistanceLabels data={designMap.distances} />
          <FitTo bounds={designBounds(designMap)} right={HERO_WIDTH + 40} />
        </>
      )}
    </>
  );
}

/** The accepted design and its distances, with room to see them round it. */
function designBounds(map: DesignMap): Bounds | null {
  const b = boundsOf(map.outline, map.distances);
  if (!b) return null;
  const pad = 0.0002; // about 20 m: the boundary it is measured from shows too
  return [b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad];
}

/** What an accepted design adds: the prefabs that fit it, and the hero. */
function Accepted({
  job,
  chain,
  onAsked,
}: {
  job: Job;
  chain: ReturnType<typeof useDesignChain>;
  onAsked: (jobId: string) => void;
}) {
  return (
    <>
      <PrefabSection job={job} chain={chain} onAsked={() => onAsked(job.id)} />
      <div className="md:fixed md:bottom-4 md:right-4 md:z-10">
        <HeroMedia
          job={job}
          parent={chain.chain.find((j) => j.id === job.parentId)}
        />
      </div>
    </>
  );
}

/** Tells the page how far the shown design has got, and whether its prefabs
 * were asked for; returns what to call when they are. */
function useProgress(
  shown: Job | undefined,
  onProgress: (progress: Progress) => void,
): (jobId: string) => void {
  const design = designState(shown);
  const [askedFor, setAskedFor] = useState<string | null>(null);
  const prefabs = askedFor !== null && askedFor === shown?.id;
  useEffect(
    () => onProgress({ design, prefabs }),
    [design, prefabs, onProgress],
  );
  return setAskedFor;
}

/** What the site's header warns of: layers that couldn't load, and a
 * design checked on the survey as it was before a change. */
function problemsOf(
  siteMap: string | null,
  designMap: string | null,
  outdated: boolean,
): string[] {
  return [
    siteMap && `The site's map couldn't load: ${siteMap}`,
    designMap && `The design's overlay couldn't load: ${designMap}`,
    outdated &&
      "The survey changed after this design was checked, so its checks may no longer hold. Ask for a change to check it again.",
  ].filter((p): p is string => Boolean(p));
}

/** How far the shown design has got, for the stepper. */
function designState(shown: Job | undefined): JourneyState["design"] {
  if (!shown) return undefined;
  if (shown.status === "queued" || shown.status === "running")
    return shown.status;
  return shown.status === "done" && shown.acceptedAttempt !== null
    ? "accepted"
    : "failed";
}

function SiteHeader({
  address,
  problems,
}: {
  address: string;
  problems: string[];
}) {
  return (
    <section className="rounded-2xl bg-zinc-950/85 px-5 py-4 shadow-2xl backdrop-blur">
      <p className="text-xs uppercase tracking-wide text-emerald-400">
        Your site
      </p>
      <p className="text-lg font-semibold">{address}</p>
      {problems.map((p) => (
        <p key={String(p)} className="mt-1 text-sm text-red-300">
          {p}
        </p>
      ))}
    </section>
  );
}
