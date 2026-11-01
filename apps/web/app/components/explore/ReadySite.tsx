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
import { SurveyPanel } from "./SurveyPanel";
import { DesignLayers, SiteLayers } from "./SiteLayers";
import type { JourneyState } from "./Stepper";
import { useDesignMap, useSiteMap } from "./useMapLayers";

/** A site that is ready: the rules drawn on it, its survey to decide, the
 * design dock, and the accepted design on the map and as a hero. It tells
 * the page how far the design has got, for the stepper. */
export function ReadySite({
  site,
  pollMs,
  onDesign,
}: {
  site: SiteState;
  pollMs: number;
  onDesign: (design: JourneyState["design"]) => void;
}) {
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false); // the survey, opened again
  const survey = useSurvey(site.id, () => setVersion((v) => v + 1));
  const siteMap = useSiteMap(site.id, version);
  const chain = useDesignChain(pollMs, site.id);
  const shown = chain.shown;
  const designMap = useDesignMap(shown);
  const accepted = shown?.status === "done" && shown.acceptedAttempt !== null;

  const design = designState(shown);
  useEffect(() => onDesign(design), [design, onDesign]);

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
        problems={[
          siteMap.problem && `The site's map couldn't load: ${siteMap.problem}`,
          designMap.problem &&
            `The design's overlay couldn't load: ${designMap.problem}`,
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
        <div className="md:fixed md:bottom-4 md:right-4 md:z-10">
          <HeroMedia
            job={shown}
            parent={chain.chain.find((j) => j.id === shown.parentId)}
          />
        </div>
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
  problems: (string | null | false)[];
}) {
  return (
    <section className="rounded-2xl bg-zinc-950/85 px-5 py-4 shadow-2xl backdrop-blur">
      <p className="text-xs uppercase tracking-wide text-emerald-400">
        Your site
      </p>
      <p className="text-lg font-semibold">{address}</p>
      {problems.filter(Boolean).map((p) => (
        <p key={String(p)} className="mt-1 text-sm text-red-300">
          {p}
        </p>
      ))}
    </section>
  );
}
