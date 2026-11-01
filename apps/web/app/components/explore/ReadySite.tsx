"use client";

import { creditOf } from "@/lib/credit";
import { useEffect, useState } from "react";

import type { Job } from "@/lib/api";
import { type Bounds, boundsOf } from "@/lib/geo";
import { type DesignMap, EMPTY_SITE_MAP, type SiteMap } from "@/lib/siteMap";
import type { SiteState } from "@/lib/sites";

import { useDesignChain } from "../useDesignChain";
import { useSurvey } from "../useSurvey";
import { FitTo } from "../map/FitTo";
import { Orbit, PITCH_3D } from "../map/View3D";
import { checkLabel } from "./AttemptRow";
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
  three,
  onProgress,
}: {
  site: SiteState;
  pollMs: number;
  three: boolean; // the map tilted: the LiDAR surface, the design standing
  onProgress: (progress: Progress) => void;
}) {
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false); // the survey, opened again
  // `version` counts the survey's changes: a design is checked on the
  // survey as it was when it was asked for.
  const chain = useDesignChain(pollMs, site.id, version);
  const survey = useSurvey(site.id, () => setVersion((v) => v + 1));
  const siteMap = useSiteMap(site.id, version);
  const shown = chain.shown;
  const designMap = useDesignMap(shown);
  const accepted = shown?.status === "done" && shown.acceptedAttempt !== null;
  // Once the survey has changed, only designs asked for since are checked
  // on it (one opened from a link was asked for before this page).
  const outdated =
    version > 0 && shown !== undefined && chain.made.get(shown.id) !== version;

  const askedPrefabs = useProgress(shown, onProgress);

  return (
    <>
      <SiteOverlays
        siteBounds={site.bounds}
        credit={siteCredit(site)}
        three={three}
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
        problems={[
          ...problemsOf(siteMap.problem, designMap.problem, outdated),
          ...undrawn(accepted ? designMap.map : null),
        ]}
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
        <Accepted job={shown} chain={chain} onPrefabs={askedPrefabs} />
      )}
    </>
  );
}

/** The credit for the site's own data, once its sources have come. */
function siteCredit(site: SiteState): string | undefined {
  return site.site ? creditOf(site.site.sources) : undefined;
}

/** What a ready site draws on the map: its rules and survey, and the
 * accepted design with its distances. */
function SiteOverlays({
  siteBounds,
  credit,
  three,
  siteMap,
  designMap,
  selected,
  onFeature,
}: {
  siteBounds: Bounds | null;
  credit: string | undefined;
  three: boolean;
  siteMap: SiteMap | null;
  designMap: DesignMap | null;
  selected: string | null;
  onFeature: (id: string) => void;
}) {
  const framed = designMap && designBounds(designMap);
  return (
    <>
      {/* The site framed, tilted as the switch says, until there is a
          design to frame (below). */}
      {!framed && <FitTo bounds={siteBounds} pitch={three ? PITCH_3D : 0} />}
      {/* Always there, empty until its data comes, so its layers are
          added first and stay under the design's (MapLibre stacks layers
          in the order they are added). */}
      <SiteLayers
        map={siteMap ?? EMPTY_SITE_MAP}
        selected={selected}
        three={three}
        credit={credit}
        onFeature={(f) => onFeature(f.id)}
      />
      {designMap && (
        <>
          <DesignLayers map={designMap} three={three} />
          <DistanceLabels data={designMap.distances} />
          {three && framed ? (
            <Orbit bounds={framed} right={HERO_WIDTH + 40} />
          ) : (
            <FitTo bounds={framed} right={HERO_WIDTH + 40} pitch={0} />
          )}
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
  onPrefabs,
}: {
  job: Job;
  chain: ReturnType<typeof useDesignChain>;
  onPrefabs: (jobId: string | null) => void;
}) {
  return (
    <>
      <PrefabSection
        job={job}
        chain={chain}
        onShown={(on) => onPrefabs(on ? job.id : null)}
      />
      <div className="xl:fixed xl:bottom-4 xl:right-4 xl:z-10">
        <HeroMedia
          job={job}
          parent={chain.chain.find((j) => j.id === job.parentId)}
        />
      </div>
    </>
  );
}

/** Tells the page how far the shown design has got, and whether its prefab
 * list is on the page; returns what to call as it comes (a job id) and goes
 * (null). */
function useProgress(
  shown: Job | undefined,
  onProgress: (progress: Progress) => void,
): (jobId: string | null) => void {
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

/** The checks the design's map couldn't draw, each with why. */
function undrawn(map: DesignMap | null): string[] {
  return (map?.unknown ?? []).map(
    (u) => `${checkLabel(u.check)} isn't drawn: ${u.reason}.`,
  );
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
