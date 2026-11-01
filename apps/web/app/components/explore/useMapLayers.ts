"use client";

import { useEffect, useState } from "react";

import type { Job } from "@/lib/api";
import {
  type DesignMap,
  type SiteMap,
  getDesignMap,
  getSiteMap,
} from "@/lib/siteMap";

/** A ready site's map layers, fetched again whenever `version` moves on (a
 * survey decision changes what is kept clear, and so the room left). */
export function useSiteMap(siteId: string | null, version: number) {
  const [map, setMap] = useState<SiteMap | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    if (siteId === null) return;
    let gone = false;
    getSiteMap(siteId).then(
      (m) => !gone && (setMap(m), setProblem(null)),
      // The old layers would show rules the server no longer holds.
      (e: Error) => !gone && (setMap(null), setProblem(e.message)),
    );
    return () => {
      gone = true;
    };
  }, [siteId, version]);
  return { map: siteId === null ? null : map, problem };
}

/** The accepted design's outline, walls and distances, once there is one,
 * or why they couldn't be read (the design still shows, with its checks). */
export function useDesignMap(job: Job | undefined) {
  const accepted =
    job?.status === "done" && job.acceptedAttempt !== null ? job.id : null;
  const [found, setFound] = useState<{
    id: string;
    map: DesignMap | null;
    problem: string | null;
  } | null>(null);
  useEffect(() => {
    if (accepted === null) return;
    let gone = false;
    getDesignMap(accepted).then(
      (map) => !gone && setFound({ id: accepted, map, problem: null }),
      (e: Error) =>
        !gone && setFound({ id: accepted, map: null, problem: e.message }),
    );
    return () => {
      gone = true;
    };
  }, [accepted]);
  return found !== null && found.id === accepted
    ? { map: found.map, problem: found.problem }
    : { map: null, problem: null };
}
