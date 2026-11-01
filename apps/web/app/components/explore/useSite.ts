"use client";

import { useEffect, useRef, useState } from "react";

import {
  type SiteState,
  createSite,
  createSiteForParcel,
  getSite,
} from "@/lib/sites";

/** The site being explored: started from an address or a clicked section,
 * followed while the server builds it, and kept in the address bar
 * (`?site=<id>`) so the page can be shared and reopened. */
export function useSite(pollMs: number) {
  const [site, setSite] = useState<SiteState | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const started = useRef(0); // the newest request: an older answer is dropped

  function follow(request: () => Promise<SiteState>) {
    const ask = ++started.current;
    request().then(
      (state) => {
        if (ask !== started.current) return;
        setProblem(null);
        setSite(state);
      },
      (e: Error) => ask === started.current && setProblem(e.message),
    );
  }

  useEffect(() => {
    const linked = new URLSearchParams(window.location.search).get("site");
    if (linked !== null) follow(() => getSite(linked));
  }, []);

  const building = site?.status === "building";
  useEffect(() => {
    if (!site || !building) return;
    const timer = setTimeout(() => follow(() => getSite(site.id)), pollMs);
    return () => clearTimeout(timer);
  }, [site, building, pollMs]);

  const id = site?.id;
  useEffect(() => {
    if (id === undefined) return;
    const url = new URL(window.location.href);
    url.searchParams.set("site", id);
    window.history.replaceState(null, "", url);
  }, [id]);

  return {
    site,
    problem,
    fromAddress: (addressId: number) => follow(() => createSite(addressId)),
    fromParcel: (parcelId: number) =>
      follow(() => createSiteForParcel(parcelId)),
  };
}
