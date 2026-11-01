"use client";

import type {
  GeoJSONSource,
  MapLayerMouseEvent,
  StyleSpecification,
} from "maplibre-gl";
import type * as GeoJSON from "geojson";
import { useEffect, useRef } from "react";

import type { FeatureCollection } from "@/lib/geo";

import { useMap } from "./BaseMap";

type LayerSpec = StyleSpecification["layers"][number];
export type Paint<T extends LayerSpec["type"]> = Extract<
  LayerSpec,
  { type: T }
>["paint"];

export interface GeoLayerProps<P> {
  id: string;
  data: FeatureCollection<P>;
  /** Drawn as `<id>-fill`, if given. */
  fill?: Paint<"fill">;
  /** Drawn as `<id>-line`, above the fill, if given. */
  line?: Paint<"line">;
  /** Stood up as `<id>-extrusion`, above the fill, if given. */
  extrusion?: Paint<"fill-extrusion">;
  /** A click on one of its features, with that feature's properties. */
  onClick?: (properties: P, lngLat: [number, number]) => void;
  /** The credit for its data, shown in the map's attribution while it is. */
  attribution?: string;
}

/** One GeoJSON layer on the surrounding map: added once, its data replaced
 * when it changes, and removed when it goes. */
export function GeoLayer<P>({
  id,
  data,
  fill,
  line,
  extrusion,
  onClick,
  attribution,
}: GeoLayerProps<P>) {
  const map = useMap();
  const click = useRef(onClick);
  const features = useRef(data.features);
  useEffect(() => {
    click.current = onClick; // the newest, for the map's handlers
    features.current = data.features;
  });

  useEffect(() => {
    if (!map) return;
    map.addSource(id, {
      type: "geojson",
      data: toGeoJSON(data),
      promoteId: "key",
      ...(attribution && { attribution }),
    });
    if (fill)
      map.addLayer({ id: `${id}-fill`, type: "fill", source: id, paint: fill });
    if (extrusion)
      map.addLayer({
        id: `${id}-extrusion`,
        type: "fill-extrusion",
        source: id,
        paint: extrusion,
      });
    if (line)
      map.addLayer({ id: `${id}-line`, type: "line", source: id, paint: line });
    const target = fill
      ? `${id}-fill`
      : extrusion
        ? `${id}-extrusion`
        : `${id}-line`;
    const clicked = (event: MapLayerMouseEvent) => {
      const index = event.features?.[0]?.properties?.index;
      const feature =
        typeof index === "number" ? features.current[index] : undefined;
      if (feature && click.current)
        click.current(feature.properties, [event.lngLat.lng, event.lngLat.lat]);
    };
    const pointer = () =>
      (map.getCanvas().style.cursor = click.current ? "pointer" : "");
    const leave = () => (map.getCanvas().style.cursor = "");
    map.on("click", target, clicked);
    map.on("mouseenter", target, pointer);
    map.on("mouseleave", target, leave);
    return () => {
      map.off("click", target, clicked);
      map.off("mouseenter", target, pointer);
      map.off("mouseleave", target, leave);
      // The map can go first (its parent's cleanup runs before this one):
      // removing it drops its style, and with it its layers and sources.
      if (!(map as { style?: unknown }).style) return;
      for (const layer of [`${id}-line`, `${id}-extrusion`, `${id}-fill`])
        if (map.getLayer(layer)) map.removeLayer(layer);
      if (map.getSource(id)) map.removeSource(id);
    };
    // Added once; its data and look follow in the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, id, attribution]);

  useEffect(() => {
    (map?.getSource(id) as GeoJSONSource | undefined)?.setData(toGeoJSON(data));
  }, [map, id, data]);

  // A changed look is applied to the layers already on the map.
  const look = JSON.stringify([fill, line, extrusion]);
  useEffect(() => {
    if (!map) return;
    const [newFill, newLine, newExtrusion] = JSON.parse(look) as [
      typeof fill,
      typeof line,
      typeof extrusion,
    ];
    for (const [layer, paint] of [
      [`${id}-fill`, newFill],
      [`${id}-line`, newLine],
      [`${id}-extrusion`, newExtrusion],
    ] as const) {
      if (!paint || !map.getLayer(layer)) continue;
      for (const [key, value] of Object.entries(paint))
        map.setPaintProperty(
          layer,
          key as Parameters<typeof map.setPaintProperty>[1],
          value,
        );
    }
  }, [map, id, look]);

  return null;
}

/** The collection as MapLibre takes it: each feature's properties flattened
 * to what its paint reads, plus its index, to find it again on a click. */
function toGeoJSON<P>(data: FeatureCollection<P>): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: data.features.map((f, index) => ({
      type: "Feature",
      properties: {
        ...(typeof f.properties === "object" ? f.properties : {}),
        index,
        key: index,
      },
      geometry: f.geometry as GeoJSON.Geometry,
    })),
  };
}
