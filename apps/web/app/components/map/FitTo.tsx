"use client";

import { useEffect } from "react";

import type { Bounds } from "@/lib/geo";

import { framing, useMap } from "./BaseMap";

/** Flies the surrounding map to `bounds` whenever they change, and frames
 * them again, at once, when the window changes shape (the panel's place
 * changes with it). */
export function FitTo({ bounds }: { bounds: Bounds | null }) {
  const map = useMap();
  const key = bounds?.join(",");
  useEffect(() => {
    if (!map || !bounds) return;
    const fit = (duration: number) =>
      map.fitBounds(bounds, { padding: framing(), duration, maxZoom: 20 });
    fit(2500);
    const refit = () => fit(0);
    window.addEventListener("resize", refit);
    return () => window.removeEventListener("resize", refit);
    // Fly again only when the bounds really change, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);
  return null;
}
