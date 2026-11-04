"use client";

import { useEffect, useState } from "react";

import type { Site } from "@/lib/api";
import { type BuildProgress, getProgress } from "@/lib/progress";
import { type Relief, getRelief } from "@/lib/relief";
import { type SiteShot, siteShots } from "@/lib/siteShots";
import type { SiteMap } from "@/lib/siteMap";

import { Picture } from "./BuildOverlay";
import { useReducedMotion, useTurn } from "./useTurn";

/** Where the design is made: its facts are chosen by it, and its own
 * pictures fill the waits. */
export interface Place {
  id: string;
  address: string;
  site?: Site | null; // its aerial and parcels, once loaded
  siteMap?: SiteMap | null; // its LINZ building outlines, once loaded
}

const SHOT_MS = 8000; // how long each of the site's pictures is shown

/** The site's own pictures (`siteShots`): what the page has, with its build
 * progress and relief asked for once. Only asked for, never made: making a
 * relief would take the GPU from Muse's run. One that can't be fetched is
 * left out, and the waits show the facts alone. */
export function useSiteShots(place: Place): SiteShot[] {
  const [progress, setProgress] = useState<BuildProgress | null>(null);
  const [relief, setRelief] = useState<Relief | null>(null);
  useEffect(() => {
    let gone = false;
    getProgress(place.id).then(
      (p) => !gone && setProgress(p),
      () => {},
    );
    getRelief(place.id).then(
      (r) => !gone && setRelief(r),
      () => {},
    );
    return () => {
      gone = true;
    };
  }, [place.id]);
  return siteShots({
    site: place.site ?? null,
    siteMap: place.siteMap ?? null,
    progress,
    relief,
  });
}

/** The site's pictures, one at a time, turning with the clock. */
export function SiteShots({ shots }: { shots: readonly SiteShot[] }) {
  const turn = useTurn(SHOT_MS);
  const shot = shots[turn % shots.length];
  if (!shot) return null;
  // TypeScript can't pair a union's kind with its entry in CAPTIONS unaided.
  const caption = (CAPTIONS[shot.kind] as (shot: SiteShot) => string)(shot);
  return (
    <figure
      aria-label={`Your site: ${caption}`}
      className="flex min-h-48 flex-1 flex-col items-center gap-2 lg:min-h-0"
    >
      <div
        key={turn}
        className="build-fade-in flex min-h-0 w-full flex-1 justify-center"
      >
        <Shot shot={shot} />
      </div>
      <figcaption className="text-sm text-zinc-300">
        Your site: {caption}
      </figcaption>
    </figure>
  );
}

const CAPTIONS: {
  [K in SiteShot["kind"]]: (shot: Extract<SiteShot, { kind: K }>) => string;
} = {
  aerial: (shot) =>
    shot.picture.survey
      ? "the LINZ aerial, its title's parcels, the buildings around it and what SAM 3.1 found"
      : "the LINZ aerial, its title's parcels and the buildings LINZ lists",
  flyover: () => "its aerial on its own LiDAR heights, a fly-over",
  depth: () => "its depth map, from its LiDAR heights",
  terrain: (shot) =>
    `its LiDAR surface, ${Math.round(shot.lowM)}–${Math.round(shot.highM)} m above sea level`,
};

const FIT = "max-h-full max-w-full rounded-xl object-contain";

function Shot({ shot }: { shot: SiteShot }) {
  switch (shot.kind) {
    case "aerial":
      return (
        <div className="aspect-square h-full max-w-full">
          <Picture progress={shot.picture} asking={null} />
        </div>
      );
    case "flyover":
      return <Flyover video={shot.video} still={shot.still} />;
    case "depth":
      return <Still src={shot.src} alt="Your site's depth map" />;
    case "terrain":
      return <Still src={shot.src} alt="Your site's LiDAR surface" />;
  }
}

function Still({ src, alt }: { src: string; alt: string }) {
  // eslint-disable-next-line @next/next/no-img-element -- the API's own image
  return <img src={src} alt={alt} className={FIT} />;
}

/** The fly-over playing, or its still for anyone who asks for less motion. */
function Flyover({ video, still }: { video: string; still: string }) {
  const less = useReducedMotion();
  if (less) return <Still src={still} alt="Your site, fly-over" />;
  return (
    <video
      src={video}
      poster={still}
      autoPlay
      muted
      loop
      playsInline
      aria-label="Your site, fly-over"
      className={FIT}
    />
  );
}
