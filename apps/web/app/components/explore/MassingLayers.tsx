"use client";

import type { Marker } from "maplibre-gl";
import { useEffect, useMemo } from "react";

import type { Placement } from "@/lib/api";
import type { LonLat } from "@/lib/geo";
import { clearanceWords, massingLayers } from "@/lib/massing";

import { useMap } from "../map/BaseMap";
import { GeoLayer } from "../map/GeoLayer";

/** A neutral grey, never the design's colours: this is where a home fits,
 * not the home Muse is designing. */
const MASSING = "#d4d4d8";
const HEIGHT_M = 1; // a low block: a massing, not a building

/** Where a home of the run's plan fits, checked, while Muse designs it
 * (#188): its outline dashed and its walls see-through in 2D, a low
 * see-through block in 3D, and a label with its clearances. */
export function MassingLayers({
  placement,
  three,
}: {
  placement: Placement;
  three: boolean;
}) {
  const layers = useMemo(() => massingLayers(placement), [placement]);
  return (
    <>
      <GeoLayer
        id="massing-outline"
        data={layers.outline}
        line={{
          "line-color": MASSING,
          "line-width": 1.5,
          "line-dasharray": [2, 2],
        }}
      />
      {three ? (
        <GeoLayer
          key="massing-3d"
          id="massing-walls"
          data={layers.walls}
          extrusion={{
            "fill-extrusion-color": MASSING,
            "fill-extrusion-base": 0,
            "fill-extrusion-height": HEIGHT_M,
            "fill-extrusion-opacity": 0.6,
          }}
        />
      ) : (
        <GeoLayer
          key="massing-2d"
          id="massing-walls"
          data={layers.walls}
          fill={{ "fill-color": MASSING, "fill-opacity": 0.35 }}
          line={{ "line-color": MASSING, "line-width": 2 }}
        />
      )}
      <MassingLabel at={layers.centre} lines={clearanceWords(placement)} />
    </>
  );
}

/** "Where a home fits (checked)", and its clearances, on the map (MapLibre's
 * text layers need a glyph server; this is a plain element on it). */
function MassingLabel({ at, lines }: { at: LonLat; lines: string[] }) {
  const map = useMap();
  const [lon, lat] = at;
  const said = lines.join(" · ");
  useEffect(() => {
    if (!map) return;
    let marker: Marker | null = null;
    let gone = false;
    import("maplibre-gl").then(({ Marker }) => {
      if (gone) return;
      const element = document.createElement("div");
      element.dataset.label = "massing";
      element.className =
        "max-w-64 rounded-md bg-zinc-900/85 px-2 py-1 text-center text-xs text-zinc-100 shadow-lg ring-1 ring-zinc-300/40";
      const title = document.createElement("p");
      title.className = "font-semibold";
      title.textContent = "Where a home fits (checked)";
      const detail = document.createElement("p");
      detail.className = "text-zinc-300";
      detail.textContent = said;
      element.append(title, detail);
      marker = new Marker({ element }).setLngLat([lon, lat]).addTo(map);
    });
    return () => {
      gone = true;
      marker?.remove();
    };
  }, [map, lon, lat, said]);
  return null;
}
