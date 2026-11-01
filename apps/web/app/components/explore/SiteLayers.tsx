"use client";

import type { DesignMap, SiteMap, SurveyedFeature } from "@/lib/siteMap";

import { GeoLayer, type Paint } from "../map/GeoLayer";

/** How each layer of the site is drawn: the rules as colour on the land. */
export const SITE_COLOURS = {
  setback: "#ef4444", // the 2 m band no dwelling may stand in
  halos: "#f97316", // 2 m around existing buildings
  keep_clear: "#22c55e", // what the owner keeps: trees, gardens
  room: "#34d399", // where a dwelling may stand
  building: "#f97316",
  undecided: "#22d3ee",
  ignore: "#a1a1aa",
  walls: "#facc15",
} as const;

const DECIDED: Paint<"fill"> = {
  "fill-color": [
    "match",
    ["coalesce", ["get", "decision"], "undecided"],
    "building",
    SITE_COLOURS.building,
    "keep_clear",
    SITE_COLOURS.keep_clear,
    "ignore",
    SITE_COLOURS.ignore,
    SITE_COLOURS.undecided,
  ],
  "fill-opacity": ["match", ["get", "decision"], "ignore", 0.15, 0.5],
};

/** The site's parcels, the setback band, the halos and keep-clear areas,
 * the room left for a dwelling, and the surveyed features, which a click
 * picks out to decide. */
export function SiteLayers({
  map,
  selected,
  onFeature,
}: {
  map: SiteMap;
  selected: string | null;
  onFeature: (feature: SurveyedFeature) => void;
}) {
  const picked = {
    type: "FeatureCollection" as const,
    features: map.features.features.filter((f) => f.properties.id === selected),
  };
  return (
    <>
      <GeoLayer
        id="site-setback"
        data={map.setback}
        fill={{ "fill-color": SITE_COLOURS.setback, "fill-opacity": 0.3 }}
      />
      <GeoLayer
        id="site-halos"
        data={map.halos}
        fill={{ "fill-color": SITE_COLOURS.halos, "fill-opacity": 0.3 }}
      />
      <GeoLayer
        id="site-room"
        data={map.room}
        fill={{ "fill-color": SITE_COLOURS.room, "fill-opacity": 0.15 }}
        line={{
          "line-color": SITE_COLOURS.room,
          "line-width": 2,
          "line-dasharray": [2, 1],
        }}
      />
      <GeoLayer
        id="site-buildings"
        data={map.buildings}
        fill={{ "fill-color": "#e4e4e7", "fill-opacity": 0.2 }}
        line={{ "line-color": "#e4e4e7", "line-width": 1 }}
      />
      <GeoLayer
        id="site-parcels"
        data={map.parcels}
        line={{ "line-color": "#ffffff", "line-width": 2.5 }}
      />
      <GeoLayer
        id="site-features"
        data={map.features}
        fill={DECIDED}
        line={{
          "line-color": "#ffffff",
          "line-width": 1.5,
          "line-opacity": 0.8,
        }}
        onClick={onFeature}
      />
      <GeoLayer
        id="site-selected"
        data={picked}
        line={{ "line-color": "#fde047", "line-width": 4 }}
      />
    </>
  );
}

/** An accepted design on the site: its outline (eaves too) and its walls. */
export function DesignLayers({ map }: { map: DesignMap }) {
  return (
    <>
      <GeoLayer
        id="design-outline"
        data={map.outline}
        fill={{ "fill-color": "#ffffff", "fill-opacity": 0.3 }}
        line={{
          "line-color": "#ffffff",
          "line-width": 1.5,
          "line-dasharray": [2, 2],
        }}
      />
      <GeoLayer
        id="design-walls"
        data={map.walls}
        fill={{ "fill-color": SITE_COLOURS.walls, "fill-opacity": 0.85 }}
        line={{ "line-color": "#422006", "line-width": 1.5 }}
      />
      <GeoLayer
        id="design-distances"
        data={map.distances}
        line={{
          "line-color": "#fde047",
          "line-width": 3,
          "line-dasharray": [1, 1],
        }}
      />
    </>
  );
}
