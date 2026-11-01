"use client";

import { useEffect } from "react";

import type { Bounds } from "@/lib/geo";

import { framing, useMap } from "./BaseMap";

/** How far the map tilts in 3D. */
export const PITCH_3D = 60;

/** Tilts the surrounding map for 3D, closer in to at least `zoom` if given
 * (buildings a few metres tall need it), or lays it flat, north up, for 2D. */
export function Tilt({ three, zoom }: { three: boolean; zoom?: number }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    const closer =
      zoom === undefined ? {} : { zoom: Math.max(map.getZoom(), zoom) };
    map.easeTo(
      three
        ? { pitch: PITCH_3D, duration: 1500, ...closer }
        : { pitch: 0, bearing: 0, duration: 1200 },
    );
    // Tilt when the view changes, not when the zoom wanted does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, three]);
  return null;
}

/** The ground as a surface, from terrain-RGB tiles (Mapbox's encoding),
 * with the aerial draped over it; flat again when it goes. */
export function Terrain({ tiles }: { tiles: string }) {
  const map = useMap();
  useEffect(() => {
    if (!map) return;
    map.addSource("terrain", {
      type: "raster-dem",
      tiles: [tiles],
      tileSize: 256,
      encoding: "mapbox",
      minzoom: 15,
      maxzoom: 20,
    });
    map.setTerrain({ source: "terrain", exaggeration: 1 });
    return () => {
      // The map may have gone first, and its style with it.
      if (!(map as { style?: unknown }).style) return;
      map.setTerrain(null);
      if (map.getSource("terrain")) map.removeSource("terrain");
    };
  }, [map, tiles]);
  return null;
}

const STOP = ["mousedown", "touchstart", "wheel", "dragstart"] as const;

/** Flies to `bounds`, tilted, then turns slowly round them until the map is
 * touched; `right` pixels are kept clear on the right. */
export function Orbit({
  bounds,
  right,
  degreesPerSecond = 4,
}: {
  bounds: Bounds;
  right?: number;
  degreesPerSecond?: number;
}) {
  const map = useMap();
  const key = bounds.join(",");
  useEffect(() => {
    if (!map) return;
    let frame = 0;
    let last = 0;
    let stopped = false;
    const spin = (now: number) => {
      if (stopped) return;
      if (last)
        map.setBearing(
          map.getBearing() + ((now - last) / 1000) * degreesPerSecond,
        );
      last = now;
      frame = requestAnimationFrame(spin);
    };
    const stop = () => {
      stopped = true;
      cancelAnimationFrame(frame);
    };
    const padding = framing(right);
    const [w, s, e, n] = bounds;
    const zoom = map.cameraForBounds(bounds, { padding })?.zoom;
    map.easeTo({
      center: [(w + e) / 2, (s + n) / 2],
      zoom,
      padding,
      pitch: PITCH_3D,
      duration: 2500,
    });
    map.once("moveend", () => {
      if (!stopped) frame = requestAnimationFrame(spin);
    });
    for (const type of STOP) map.on(type, stop);
    return () => {
      stop();
      for (const type of STOP) map.off(type, stop);
    };
    // Fly again only when the bounds really change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key, right, degreesPerSecond]);
  return null;
}

/** A 2D/3D switch for the map. */
export function ViewToggle({
  three,
  onChange,
}: {
  three: boolean;
  onChange: (three: boolean) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Map view"
      className="flex rounded-full bg-zinc-950/80 p-1 text-sm font-semibold shadow-lg backdrop-blur"
    >
      {[false, true].map((value) => (
        <button
          key={String(value)}
          type="button"
          aria-pressed={three === value}
          onClick={() => onChange(value)}
          className={`rounded-full px-3 py-1 ${
            three === value
              ? "bg-emerald-400 text-zinc-950"
              : "text-zinc-300 hover:text-white"
          }`}
        >
          {value ? "3D" : "2D"}
        </button>
      ))}
    </div>
  );
}
