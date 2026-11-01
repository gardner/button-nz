"use client";

import type { ExpressionSpecification } from "maplibre-gl";
import { useEffect } from "react";

import type { Bounds } from "@/lib/geo";

import { framing, useMap } from "./BaseMap";

/** How far the map tilts in 3D. */
export const PITCH_3D = 60;

/** A thing's own height, top less bottom (`heightM`, `baseM`), to extrude
 * from the aerial's 0. On a flat map with no terrain it then stands on the
 * photo, however far its ground is above the site's datum. */
export const OWN_HEIGHT: ExpressionSpecification = [
  "-",
  ["get", "heightM"],
  ["get", "baseM"],
];

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
