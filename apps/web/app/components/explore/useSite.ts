"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/fields";
import {
  type SiteState,
  createSite,
  createSiteForParcel,
  getSite,
} from "@/lib/sites";

/** The site being explored: started from an address or a clicked section,
 * followed while the server builds it, and kept in the address bar
 * (`?site=<id>`) so the page can be shared and reopened. A poll that fails
 * for a moment (a 502 while the API restarts, a timeout) is retried; one the
 * API refuses for good stops the following, with its reason shown. */
export function useSite(pollMs: number) {
  const [site, setSite] = useState<SiteState | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  // The newest site asked for. Only a person's pick moves it on; a poll
  // checks it, so a late answer about an older site never replaces a newer one.
  const picked = useRef(0);

  function pick(request: () => Promise<SiteState>) {
    const ask = ++picked.current;
    request().then(
      (state) => {
        if (ask !== picked.current) return;
        setProblem(null);
        setSite(state);
      },
      (e: Error) => {
        if (ask !== picked.current) return;
        setProblem(e.message);
        setRetries((n) => n + 1); // keep following the site still on show
      },
    );
  }

  useEffect(() => {
    const linked = new URLSearchParams(window.location.search).get("site");
    if (linked !== null) pick(() => getSite(linked));
  }, []);

  const building = site?.status === "building";
  useEffect(() => {
    if (!site || !building) return;
    const ask = picked.current;
    const timer = setTimeout(() => {
      getSite(site.id).then(
        (state) => {
          if (ask !== picked.current) return;
          setProblem(null);
          setSite(state);
        },
        (e: Error) => {
          if (ask !== picked.current) return;
          setProblem(e.message);
          if (!(e instanceof ApiError) || e.transient) setRetries((n) => n + 1);
        },
      );
    }, pollMs);
    return () => clearTimeout(timer);
  }, [site, building, pollMs, retries]);

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
    fromAddress: (addressId: number) => pick(() => createSite(addressId)),
    fromParcel: (parcelId: number) => pick(() => createSiteForParcel(parcelId)),
  };
}
