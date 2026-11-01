"use client";

import type { Marker } from "maplibre-gl";
import { useEffect } from "react";

import type { FeatureCollection, LonLat } from "@/lib/geo";
import type { Distance } from "@/lib/siteMap";

import { useMap } from "../map/BaseMap";

/** What a distance label says: the measured distance against the rule's. */
export function distanceLabel({ metres, required }: Distance): string {
  return `${metres.toFixed(1)} m ${metres >= required ? "≥" : "<"} ${required} m`;
}

/** The midpoint of a LineString's ends: where its label goes. */
export function midpoint(coordinates: unknown): LonLat | null {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return null;
  const [a, b] = [coordinates[0], coordinates.at(-1)] as LonLat[];
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

/** A label on each distance line of an accepted design (MapLibre's text
 * layers need a glyph server; these are plain elements on the map). */
export function DistanceLabels({
  data,
}: {
  data: FeatureCollection<Distance>;
}) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    let markers: Marker[] = [];
    let gone = false;
    import("maplibre-gl").then(({ Marker }) => {
      if (gone) return;
      markers = data.features.flatMap((f) => {
        const at = midpoint(f.geometry.coordinates);
        if (!at) return [];
        const element = document.createElement("div");
        const ok = f.properties.metres >= f.properties.required;
        element.className = `rounded-md px-2 py-0.5 text-xs font-semibold shadow-lg ${
          ok ? "bg-emerald-500 text-zinc-950" : "bg-red-500 text-white"
        }`;
        element.textContent = distanceLabel(f.properties);
        element.dataset.label = "distance";
        return [new Marker({ element }).setLngLat(at).addTo(map)];
      });
    });
    return () => {
      gone = true;
      markers.forEach((m) => m.remove());
    };
  }, [map, data]);
  return null;
}
