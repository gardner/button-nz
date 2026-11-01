"use client";

import { useState } from "react";

import type { Job } from "@/lib/api";
import type { Product } from "@/lib/products";

import { GeoLayer } from "../map/GeoLayer";
import type { useDesignChain } from "../useDesignChain";
import { PrefabPanel } from "./PrefabPanel";

/** The prefabs that fit the accepted design: the one pointed at drawn on the
 * map where it would stand, and any placed as a new design with the same
 * brief, its walls fixed to the product's footprint. */
export function PrefabSection({
  job,
  chain,
  onShown,
}: {
  job: Job;
  chain: ReturnType<typeof useDesignChain>;
  onShown: (shown: boolean) => void;
}) {
  const [hovered, setHovered] = useState<Product | null>(null);
  return (
    <>
      {hovered?.placedFootprint && (
        <GeoLayer
          id="prefab-footprint"
          data={hovered.placedFootprint}
          fill={{ "fill-color": "#38bdf8", "fill-opacity": 0.45 }}
          line={{ "line-color": "#e0f2fe", "line-width": 2 }}
        />
      )}
      <PrefabPanel
        key={job.id}
        jobId={job.id}
        busy={chain.busy}
        onShown={onShown}
        onHover={setHovered}
        onPlace={(p) => {
          setHovered(null);
          chain.design(job.brief, job.allowObservations, p.id);
        }}
      />
    </>
  );
}
