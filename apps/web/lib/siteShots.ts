/**
 * The site's own pictures, to fill the waits between Muse's artifacts: its
 * aerial with its parcels and LINZ building outlines, its fly-over (or depth
 * map), and its terrain preview. All of them are already made and served by
 * the API; nothing here asks for anything to be made.
 */

import type { Site } from "./api";
import type { Geometry, LonLat } from "./geo";
import { toNztm } from "./nztm";
import type { BuildProgress, Ring } from "./progress";
import { type Relief, shownClip } from "./relief";
import type { SiteMap } from "./siteMap";

export type SiteShot =
  | { kind: "aerial"; picture: BuildProgress } // drawn as the build overlay draws it
  | { kind: "flyover"; video: string; still: string }
  | { kind: "depth"; src: string }
  | { kind: "terrain"; src: string; lowM: number; highM: number };

/** What the site's pictures are made from, each null until it has come. */
export interface SiteSources {
  site: Site | null;
  siteMap: SiteMap | null;
  progress: BuildProgress | null; // GET /sites/{id}/progress
  relief: Relief | null; // GET /sites/{id}/relief
}

/** The site's pictures that exist, in the order to show them. */
export function siteShots(sources: SiteSources): SiteShot[] {
  return [
    aerialShot(sources),
    reliefShot(sources.relief),
    terrainShot(sources.progress),
  ].filter((shot): shot is SiteShot => shot !== null);
}

/** The build's own picture where it recorded one (with SAM's finds), else
 * the site's aerial with its parcels and the site map's building outlines. */
function aerialShot({ site, siteMap, progress }: SiteSources): SiteShot | null {
  if (progress?.frame && progress.aerial)
    return { kind: "aerial", picture: progress };
  if (!site?.aerial) return null;
  return {
    kind: "aerial",
    picture: {
      frame: site.aerial.bbox,
      parcels: site.parcels.map((p) => p.ring),
      buildings: (siteMap?.buildings.features ?? []).flatMap((f) =>
        outerRings(f.geometry),
      ),
      terrain: null,
      aerial: site.aerial,
      survey: null,
    },
  };
}

/** A polygon's outline (or each of a multipolygon's), in NZTM. */
function outerRings(geometry: Geometry): Ring[] {
  const polygons =
    geometry.type === "Polygon"
      ? [geometry.coordinates as LonLat[][]]
      : geometry.type === "MultiPolygon"
        ? (geometry.coordinates as LonLat[][][])
        : [];
  return polygons.map(([outer]) => outer.map(toNztm));
}

/** The fly-over (or parallax clip) if one is ready, else the depth map. */
function reliefShot(relief: Relief | null): SiteShot | null {
  if (!relief) return null;
  const clip = shownClip(relief);
  if (clip) return { kind: "flyover", video: clip.video, still: clip.still };
  const depth = relief.tiers.find(
    (t) => t.tier === "depth" && t.status === "ready",
  );
  return depth?.files.preview
    ? { kind: "depth", src: depth.files.preview }
    : null;
}

function terrainShot(progress: BuildProgress | null): SiteShot | null {
  const terrain = progress?.terrain;
  return terrain
    ? {
        kind: "terrain",
        src: terrain.url,
        lowM: terrain.lowM,
        highM: terrain.highM,
      }
    : null;
}
