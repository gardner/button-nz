"use client";

import { useEffect } from "react";

import type { Bounds } from "@/lib/geo";

import { framing, useMap } from "./BaseMap";

/** Flies the surrounding map to `bounds` whenever they change, leaving
 * `right` pixels clear on the right (for a panel there). */
export function FitTo({
  bounds,
  right,
}: {
  bounds: Bounds | null;
  right?: number;
}) {
  const map = useMap();
  const key = bounds?.join(",");
  useEffect(() => {
    if (!map || !bounds) return;
    map.fitBounds(bounds, {
      padding: framing(right),
      duration: 2500,
      maxZoom: 20,
    });
    // Fly again only when the bounds really change, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key, right]);
  return null;
}
