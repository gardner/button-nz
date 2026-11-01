"use client";

import { useEffect, useState } from "react";

import { passing } from "@/lib/fields";
import { type Town, getTown } from "@/lib/sites";

import { BaseMap, REEFTON } from "../map/BaseMap";
import { FitTo } from "../map/FitTo";
import { GeoLayer, type Paint } from "../map/GeoLayer";
import { BuildProgress } from "./BuildProgress";
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

/** Once a site is chosen, the town steps back behind it. */
const TOWN_FILL_BEHIND: Paint<"fill"> = { ...TOWN_FILL, "fill-opacity": 0.12 };

const TOWN_LINE: Paint<"line"> = {
  "line-color": "#ffffff",
  "line-opacity": 0.5,
  "line-width": 0.6,
};

/** Map-first: Reefton's sections coloured by the town screen, any address
 * found and its site built live, with the journey's progress always on show. */
export function Explore({ pollMs = 1500 }: { pollMs?: number }) {
  const { site, problem, fromAddress } = useSite(pollMs);
  const town = useTown("reefton", pollMs);
  const step = stepOf({ site: site?.status });
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-zinc-950 text-white">
      <BaseMap bounds={REEFTON}>
        {town.data && (
          <GeoLayer
            id="town"
            data={town.data.sections}
            fill={site ? TOWN_FILL_BEHIND : TOWN_FILL}
            line={TOWN_LINE}
          />
        )}
        <FitTo bounds={site?.bounds ?? null} />
      </BaseMap>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-[560px] max-w-full bg-gradient-to-r from-zinc-950/85 via-zinc-950/50 to-transparent"
      />
      <header className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between gap-4 p-4">
        <p className="hidden rounded-full bg-zinc-950/70 px-4 py-2 text-lg font-semibold tracking-tight shadow-lg backdrop-blur md:block">
          Button <span className="text-emerald-400">NZ</span>
        </p>
        <div className="pointer-events-auto">
          <Stepper current={step} />
        </div>
        <span className="hidden w-32 md:block" aria-hidden />
      </header>
      <Panel
        site={site}
        problem={problem}
        town={town}
        onAddress={(id) => fromAddress(id)}
      />
    </main>
  );
}

/** The panel over the map's left: the pitch, the search, and the town's
 * headline or the site being built. */
function Panel({
  site,
  problem,
  town,
  onAddress,
}: {
  site: ReturnType<typeof useSite>["site"];
  problem: string | null;
  town: ReturnType<typeof useTown>;
  onAddress: (addressId: number) => void;
}) {
  return (
    <aside className="absolute left-4 top-20 flex max-h-[calc(100%-6rem)] w-[min(440px,calc(100%-2rem))] flex-col gap-4 overflow-y-auto pb-4 pr-1">
      <h1 className="text-4xl font-semibold leading-tight tracking-tight drop-shadow-lg">
        Unlock the housing hiding in your backyard
      </h1>
      <SearchBox onPick={(a) => onAddress(a.id)} autoFocus />
      {problem && (
        <p role="alert" className="rounded-xl bg-red-900/85 px-4 py-3 text-sm">
          {problem}
        </p>
      )}
      {site ? (
        <SiteCard site={site} />
      ) : (
        town.data && <TownOverview town={town.data} name="Reefton" />
      )}
      {town.problem && (
        <p className="rounded-xl bg-zinc-950/80 px-4 py-3 text-sm text-zinc-300">
          The town map couldn&apos;t load: {town.problem}
        </p>
      )}
    </aside>
  );
}

function SiteCard({
  site,
}: {
  site: NonNullable<ReturnType<typeof useSite>["site"]>;
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
    <section className="rounded-2xl bg-zinc-950/85 p-5 shadow-2xl backdrop-blur">
      <p className="text-sm text-emerald-400">Site ready</p>
      <p className="text-xl font-semibold">{site.address}</p>
      <p className="mt-1 text-sm text-zinc-400">
        Title {site.site?.title} · its parcels, LiDAR, aerial and survey are in.
      </p>
    </section>
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
