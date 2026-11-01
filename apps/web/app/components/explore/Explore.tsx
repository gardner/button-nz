"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { passing } from "@/lib/fields";
import { measured } from "@/lib/siteMap";
import {
  type SiteState,
  type Town,
  type TownSection,
  getTown,
} from "@/lib/sites";

import { BaseMap, REEFTON, framing, unpad, useMap } from "../map/BaseMap";
import { Credit, GeoLayer, type Paint } from "../map/GeoLayer";
import {
  CONTEXT_HEIGHT,
  OWN_HEIGHT,
  PITCH_3D,
  ViewToggle,
} from "../map/View3D";
import { BuildProgress } from "./BuildProgress";
import { type Progress, ReadySite } from "./ReadySite";
import { SearchBox } from "./SearchBox";
import { Stepper, stepOf } from "./Stepper";
import { TOWN_COLOURS, TownOverview } from "./TownOverview";
import { useSite } from "./useSite";

const TOWN_FILL: Paint<"fill"> = {
  "fill-color": [
    "match",
    ["get", "category"],
    "clear",
    TOWN_COLOURS.clear,
    "outlines",
    TOWN_COLOURS.outlines,
    TOWN_COLOURS.none,
  ],
  "fill-opacity": ["match", ["get", "category"], "none", 0.2, 0.55],
};

/** Reefton's urban aerial photos, under the town's sections. */
const TOWN_CREDIT =
  "Reefton: Buller 0.075m Urban Aerial Photos (2024-2025): Toitū Te Whenua " +
  "Land Information New Zealand, Aerial Surveys, Buller District Council, CC BY 4.0";

/** Once a site is chosen, the town steps back behind it. */
const TOWN_FILL_BEHIND: Paint<"fill"> = { ...TOWN_FILL, "fill-opacity": 0.12 };

const TOWN_LINE: Paint<"line"> = {
  "line-color": "#ffffff",
  "line-opacity": 0.5,
  "line-width": 0.6,
};

/** How close the town comes in 3D, for its buildings to show. */
const TOWN_ZOOM_3D = 15.8;

/** The town's buildings stood up in 3D, as tall as the LiDAR says, light so
 * they stand out from the sections' colours, warmer the taller. */
const TOWN_BUILDINGS_3D: Paint<"fill-extrusion"> = {
  "fill-extrusion-color": [
    "interpolate",
    ["linear"],
    OWN_HEIGHT,
    2,
    "#fafaf9",
    8,
    "#fef3c7",
    16,
    "#fdba74",
  ],
  "fill-extrusion-height": CONTEXT_HEIGHT,
  "fill-extrusion-base": 0,
  "fill-extrusion-opacity": 0.9,
};

/** Map-first: Reefton's sections coloured by the town screen, any address
 * found and its site built live, then surveyed, designed and checked on the
 * map, with the journey's progress always on show. */
export function Explore({ pollMs = 1500 }: { pollMs?: number }) {
  const { site, problem, opening, fromAddress, fromSection } = useSite(pollMs);
  const town = useTown("reefton", pollMs);
  const { progress, three, setThree, onProgress } = useJourney();
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-zinc-950 text-white">
      <BaseMap bounds={REEFTON}>
        {town.data && (
          <TownLayers
            town={town.data}
            behind={site !== null}
            standing={three && site?.status !== "ready"}
            // A ready site's own shapes lie over the town: a tap there is
            // for them, so another section is found by its address.
            onSection={site?.status === "ready" ? undefined : fromSection}
          />
        )}
        <Camera site={site} town={town.data} three={three} />
        {/* Reefton's photos are credited always: the map can be panned
            back to the town from any site, and naming a provider whose
            photos are off screen is no harm. A ready site adds its own. */}
        <Credit id="town-credit" text={TOWN_CREDIT} />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 w-[560px] max-w-full bg-gradient-to-r from-zinc-950/85 via-zinc-950/50 to-transparent"
        />
        <Header
          step={stepOf({ site: site?.status, ...progress })}
          three={three}
          onThree={setThree}
        />
        <SidePanel
          site={site}
          problem={problem}
          opening={opening}
          town={town}
          pollMs={pollMs}
          three={three}
          onAddress={fromAddress}
          onProgress={onProgress}
        />
      </BaseMap>
    </main>
  );
}

/** Where the map looks until a site is ready (and while a new one builds):
 * the town. A ready site moves the camera itself (ReadySite: its fit and
 * orbit), so no two moves start at once and stop each other. */
function Camera({
  site,
  town,
  three,
}: {
  site: SiteState | null;
  town: Town | null;
  three: boolean;
}) {
  if (site?.status === "ready") return null;
  return <TownView three={three} loaded={town !== null} />;
}

/** The town, framed flat in 2D, or tilted and closer in for 3D (its
 * buildings are a few metres tall): one move each time the view changes,
 * the town arrives (its headline changes the panel) or the map resizes. */
function TownView({ three, loaded }: { three: boolean; loaded: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    const look = (duration: number) => {
      const padding = framing();
      unpad(map); // an earlier ease's padding would be added to this one
      if (!three)
        return map.fitBounds(REEFTON, {
          padding,
          pitch: 0,
          bearing: 0,
          duration,
        });
      const [w, s, e, n] = REEFTON;
      map.easeTo({
        center: [(w + e) / 2, (s + n) / 2],
        zoom: TOWN_ZOOM_3D, // the town's own, not a site's close-up
        pitch: PITCH_3D,
        padding,
        duration,
      });
    };
    look(1500);
    const again = () => look(0);
    map.on("resize", again);
    return () => {
      map.off("resize", again);
    };
  }, [map, three, loaded]);
  return null;
}

/** How far the journey has got, for the stepper, and whether the map is in
 * 3D: it goes 3D when a design is accepted, to see it stand there. */
function useJourney() {
  const [progress, setProgress] = useState<Progress>({});
  const [three, setThree] = useState(false);
  const wasAccepted = useRef(false);
  const onProgress = useCallback((now: Progress) => {
    setProgress(now);
    const accepted = now.design === "accepted";
    if (accepted && !wasAccepted.current) setThree(true);
    wasAccepted.current = accepted;
  }, []);
  return { progress, three, setThree, onProgress };
}

/** The town's sections, stepped back once a site is chosen, and in 3D its
 * buildings standing, until a ready site stands its own. */
function TownLayers({
  town,
  behind,
  standing,
  onSection,
}: {
  town: Town;
  behind: boolean;
  standing: boolean; // 3D, with no ready site's own buildings to show
  onSection?: (parcelId: number) => void; // a section tapped, by its parcel
}) {
  return (
    <>
      <GeoLayer
        id="town"
        data={town.sections}
        fill={behind ? TOWN_FILL_BEHIND : TOWN_FILL}
        line={TOWN_LINE}
        onClick={onSection && ((section: TownSection) => onSection(section.id))}
      />
      {standing && (
        <GeoLayer
          id="town-buildings"
          data={measured(town.buildings)}
          extrusion={TOWN_BUILDINGS_3D}
        />
      )}
    </>
  );
}

function Header({
  step,
  three,
  onThree,
}: {
  step: ReturnType<typeof stepOf>;
  three: boolean;
  onThree: (three: boolean) => void;
}) {
  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between gap-4 p-4">
      <p className="hidden rounded-full bg-zinc-950/70 px-4 py-2 text-lg font-semibold tracking-tight shadow-lg backdrop-blur md:block">
        Button <span className="text-emerald-400">NZ</span>
      </p>
      <div className="pointer-events-auto">
        <Stepper current={step} />
      </div>
      <div className="pointer-events-auto">
        <ViewToggle three={three} onChange={onThree} />
      </div>
    </header>
  );
}

/** The panel over the map's left: the pitch and the town's headline, the
 * search, the site being built, then the ready site's survey and design. */
function SidePanel({
  site,
  problem,
  opening,
  town,
  pollMs,
  three,
  onAddress,
  onProgress,
}: {
  site: SiteState | null;
  problem: string | null;
  opening: string | null;
  town: ReturnType<typeof useTown>;
  pollMs: number;
  three: boolean;
  onAddress: (addressId: number, address: string) => void;
  onProgress: (progress: Progress) => void;
}) {
  return (
    <aside
      data-map-panel
      className="absolute left-4 top-20 flex max-h-[calc(100%-6rem)] w-[min(440px,calc(100%-2rem))] flex-col gap-4 overflow-y-auto pb-4 pr-1"
    >
      {!site && (
        <h1 className="text-2xl font-semibold leading-snug tracking-tight drop-shadow-lg">
          Unlock the housing hiding in your backyard
        </h1>
      )}
      <SearchBox onPick={(a) => onAddress(a.id, a.address)} autoFocus />
      {problem && (
        <p role="alert" className="rounded-xl bg-red-900/85 px-4 py-3 text-sm">
          {problem}
        </p>
      )}
      {!site && town.data && <TownOverview town={town.data} name="Reefton" />}
      {opening && (
        <p
          aria-live="polite"
          className="rounded-xl bg-zinc-950/85 px-4 py-3 text-sm"
        >
          Opening {opening}…
        </p>
      )}
      {site && (
        <SiteSection
          site={site}
          held={opening !== null}
          pollMs={pollMs}
          three={three}
          onProgress={onProgress}
        />
      )}
      {town.problem && (
        <p className="rounded-xl bg-zinc-950/80 px-4 py-3 text-sm text-zinc-300">
          The town map couldn&apos;t load: {town.problem}
        </p>
      )}
    </aside>
  );
}

/** The site: its build while it is built, then the ready site, held while
 * another address opens (a design asked for then would be for the site
 * about to go). */
function SiteSection({
  site,
  held,
  pollMs,
  three,
  onProgress,
}: {
  site: SiteState;
  held: boolean;
  pollMs: number;
  three: boolean;
  onProgress: (progress: Progress) => void;
}) {
  if (site.status !== "ready")
    return (
      <BuildProgress
        address={site.address}
        status={site.status}
        step={site.step}
        error={site.error}
      />
    );
  return (
    <fieldset disabled={held} className="contents">
      <ReadySite
        key={site.id}
        site={site}
        pollMs={pollMs}
        three={three}
        onProgress={onProgress}
      />
    </fieldset>
  );
}

/** The town's sections; a failure that passes is asked again `retryMs` on. */
function useTown(slug: string, retryMs: number) {
  const [data, setData] = useState<Town | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let gone = false;
    const timer = setTimeout(
      () =>
        getTown(slug).then(
          (town) => !gone && (setData(town), setProblem(null)),
          (e: Error) => {
            if (gone) return;
            setProblem(e.message);
            if (passing(e)) setTries((n) => n + 1);
          },
        ),
      tries === 0 ? 0 : retryMs,
    );
    return () => {
      gone = true;
      clearTimeout(timer);
    };
  }, [slug, tries]); // eslint-disable-line react-hooks/exhaustive-deps -- retryMs only paces
  return { data, problem };
}
