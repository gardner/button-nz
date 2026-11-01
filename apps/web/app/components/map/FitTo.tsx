"use client";

import { useEffect } from "react";

import type { Bounds } from "@/lib/geo";

import { framing, useMap } from "./BaseMap";

/** Flies the surrounding map to `bounds` whenever they change. */
export function FitTo({ bounds }: { bounds: Bounds | null }) {
  const map = useMap();
  const key = bounds?.join(",");
  useEffect(() => {
    if (!map || !bounds) return;
    map.fitBounds(bounds, { padding: framing(), duration: 2500, maxZoom: 20 });
    // Fly again only when the bounds really change, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);
  return null;
}
