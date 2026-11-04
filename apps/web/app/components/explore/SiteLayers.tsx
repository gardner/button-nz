"use client";

import type { ExpressionSpecification } from "maplibre-gl";

import {
  type DesignMap,
  type SiteMap,
  EMPTY_SITE_MAP,
  type SurveyedFeature,
  measured,
} from "@/lib/siteMap";

import { GeoLayer, type Paint } from "../map/GeoLayer";
import { CONTEXT_HEIGHT, OWN_HEIGHT } from "../map/View3D";

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

/** A surveyed feature's colour, by what it was decided to be. */
const DECIDED_COLOUR = [
  "match",
  ["coalesce", ["get", "decision"], "undecided"],
  "building",
  SITE_COLOURS.building,
  "keep_clear",
  SITE_COLOURS.keep_clear,
  "ignore",
  SITE_COLOURS.ignore,
  SITE_COLOURS.undecided,
] as NonNullable<Paint<"line">>["line-color"];

/** The survey drawn see-through, so the owner sees what they are judging:
 * the photo shows through (the fill stays, unseen, as what a click hits),
 * and the kind is in a thick outline, faint for what is ignored. */
const SURVEY_FILL: Paint<"fill"> = {
  "fill-color": "#000000",
  "fill-opacity": 0,
};
const SURVEY_LINE: Paint<"line"> = {
  "line-color": DECIDED_COLOUR,
  "line-width": 3,
  "line-opacity": ["match", ["get", "decision"], "ignore", 0.45, 0.95],
};

/** In 3D the site's buildings and trees stand at half what the LiDAR says
 * (`CONTEXT_SCALE`), so the proposed dwelling isn't crowded:
 * buildings in stone, trees in green, a little see-through so the rules on
 * the ground show between them. */
const BUILDINGS_3D: Paint<"fill-extrusion"> = {
  "fill-extrusion-color": "#d6d3d1",
  "fill-extrusion-base": 0,
  "fill-extrusion-height": CONTEXT_HEIGHT,
  "fill-extrusion-opacity": 0.85,
};
const CANOPY_3D: Paint<"fill-extrusion"> = {
  "fill-extrusion-color": "#4d7c0f",
  "fill-extrusion-base": 0,
  "fill-extrusion-height": CONTEXT_HEIGHT,
  "fill-extrusion-opacity": 0.75,
};

/** The site's buildings and trees standing (3D only). */
function Standing({ map }: { map: SiteMap }) {
  return (
    <>
      <GeoLayer
        id="site-standing-buildings"
        data={measured(map.buildings)}
        extrusion={BUILDINGS_3D}
      />
      <GeoLayer
        id="site-canopy"
        data={measured(map.canopy)}
        extrusion={CANOPY_3D}
      />
      {/* What the owner confirmed as a building, LINZ outline or not. */}
      <GeoLayer
        id="site-confirmed"
        data={measured({
          ...map.features,
          features: map.features.features.filter(
            (f) => f.properties.decision === "building",
          ),
        })}
        extrusion={BUILDINGS_3D}
      />
    </>
  );
}

/** The site's parcels, the setback band, the halos and keep-clear areas,
 * the room left for a dwelling, and the surveyed features, which a click
 * picks out to decide. */
export function SiteLayers({
  map,
  selected,
  three = false,
  credit,
  onFeature,
}: {
  map: SiteMap;
  selected: string | null;
  three?: boolean;
  credit?: string; // the site's own data's providers
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
        attribution={credit}
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
        fill={SURVEY_FILL}
        line={SURVEY_LINE}
        onClick={onFeature}
      />
      {/* Always mounted (empty in 2D), so its layers stay under the
          picked feature's outline whenever 3D comes on. */}
      <Standing map={three ? map : EMPTY_SITE_MAP} />
      <GeoLayer
        id="site-selected"
        data={picked}
        line={{ "line-color": "#fde047", "line-width": 4 }}
      />
    </>
  );
}

/** The design stood up in place in the finishes its render used (a placed
 * product's, or the bespoke defaults): its walls, and on them a slab of roof
 * over its outline, eaves and all. The roof starts where the walls stop, so
 * no two faces are coplanar (two tops at one height z-fight: the roof
 * tears). */
const ROOF_DEPTH = 0.5; // metres: a flat stand-in for its pitched roof
const EAVES_LINE: ExpressionSpecification = [
  "max",
  ["-", OWN_HEIGHT, ROOF_DEPTH],
  0,
];
function walls3d(colour: string): Paint<"fill-extrusion"> {
  return {
    "fill-extrusion-color": colour,
    "fill-extrusion-base": 0,
    "fill-extrusion-height": EAVES_LINE,
    "fill-extrusion-opacity": 1,
  };
}
function roof3d(colour: string): Paint<"fill-extrusion"> {
  return {
    "fill-extrusion-color": colour,
    "fill-extrusion-base": EAVES_LINE,
    "fill-extrusion-height": OWN_HEIGHT,
    "fill-extrusion-opacity": 1,
  };
}

/** An accepted design on the site: its outline (eaves too) and its walls,
 * flat, or in 3D standing in place, roofed. */
export function DesignLayers({
  map,
  three,
}: {
  map: DesignMap;
  three: boolean;
}) {
  // A design whose heights weren't measured is drawn flat, even in 3D.
  if (three && measured(map.walls).features.length > 0)
    return (
      <>
        <GeoLayer
          key="walls-3d"
          id="design-walls"
          data={measured(map.walls)}
          extrusion={walls3d(map.finishes.walls)}
        />
        <GeoLayer
          key="roof-3d"
          id="design-outline"
          data={measured(map.outline)}
          extrusion={roof3d(map.finishes.roof)}
        />
        <Distances key="distances-3d" map={map} />
      </>
    );
  return (
    <>
      <GeoLayer
        key="outline-2d"
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
        key="walls-2d"
        id="design-walls"
        data={map.walls}
        fill={{ "fill-color": SITE_COLOURS.walls, "fill-opacity": 0.85 }}
        line={{ "line-color": "#422006", "line-width": 1.5 }}
      />
      <Distances key="distances-2d" map={map} />
    </>
  );
}

/** Keyed with the view, so it is added again after the design's layers
 * and stays above them. */
function Distances({ map }: { map: DesignMap }) {
  return (
    <GeoLayer
      id="design-distances"
      data={map.distances}
      line={{
        "line-color": "#fde047",
        "line-width": 3,
        "line-dasharray": [1, 1],
      }}
    />
  );
}
