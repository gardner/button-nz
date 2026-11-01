"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, passing } from "@/lib/fields";
import { getDesign } from "@/lib/api";
import {
  type SiteState,
  createSite,
  createSiteFromSection,
  getSite,
} from "@/lib/sites";

/** A site asked for and not yet answered: the request (safe to repeat: one
 * site per address), the pick it answers, and how often it has been asked. */
interface Asking {
  request: () => Promise<SiteState>;
  ask: number;
  tries: number;
  label: string | null; // what is being opened, in words (none for a link)
}

/** The site being explored: started from an address (or opened from a
 * link), followed while the server builds it, and kept in the address bar
 * (`?site=<id>`) so the page can be shared and reopened. A pick or a poll
 * that fails for a moment (a 502 while the API restarts, a dropped
 * connection) is asked again; one the API refuses for good stops, with its
 * reason shown. */
export function useSite(pollMs: number) {
  const [site, setSite] = useState<SiteState | null>(null);
  // Why a pick failed stays until the next pick; why a poll failed, until
  // the next poll answers. A poll can't clear a pick's reason.
  const [pickProblem, setPickProblem] = useState<string | null>(null);
  const [pollProblem, setPollProblem] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  // The newest site asked for. Only a pick moves it on; everything that
  // answers checks it, so a late answer about an older site never wins.
  const picked = useRef(0);
  // The link's site is the first pick, asked for as the page opens.
  const [asking, setAsking] = useState<Asking | null>(() => {
    const request = linkedSite();
    return request && { request, ask: 0, tries: 0, label: null };
  });

  function pick(request: () => Promise<SiteState>, label: string) {
    setPickProblem(null); // a new pick starts with no reason left over
    setPollProblem(null);
    setAsking({ request, ask: ++picked.current, tries: 0, label });
  }

  useEffect(() => {
    if (asking === null) return;
    const { request, ask, tries, label } = asking;
    let gone = false; // a newer pick has replaced this one
    const timer = setTimeout(
      () =>
        request().then(
          (state) => {
            if (gone || ask !== picked.current) return;
            setAsking(null);
            setPickProblem(null);
            setPollProblem(null);
            setSite(state);
          },
          (e: Error) => {
            if (gone || ask !== picked.current) return;
            setPickProblem(e.message);
            setRetries((n) => n + 1); // keep following the site still on show
            setAsking(
              again(e) ? { request, ask, tries: tries + 1, label } : null,
            );
          },
        ),
      tries === 0 ? 0 : pollMs,
    );
    return () => {
      gone = true;
      clearTimeout(timer);
    };
  }, [asking]); // eslint-disable-line react-hooks/exhaustive-deps -- pollMs only paces

  const building = site?.status === "building";
  useEffect(() => {
    if (!site || !building) return;
    const ask = picked.current;
    const timer = setTimeout(() => {
      getSite(site.id).then(
        (state) => {
          if (ask !== picked.current) return;
          setPollProblem(null);
          // Only the site it polled: a pick may have answered meanwhile.
          setSite((shown) => (shown?.id === state.id ? state : shown));
        },
        (e: Error) => {
          if (ask !== picked.current) return;
          setPollProblem(e.message);
          if (passing(e)) setRetries((n) => n + 1);
        },
      );
    }, pollMs);
    return () => clearTimeout(timer);
  }, [site, building, pollMs, retries]);

  const id = site?.id;
  useEffect(() => {
    if (id === undefined) return;
    const url = new URL(window.location.href);
    // The link's design goes with the site the link opened (a link with a
    // design alone named no site: the design's is the one opened), never
    // with a site picked since.
    const fromLink = picked.current === 0;
    const before = url.searchParams.get("site");
    if (!fromLink && before !== id) url.searchParams.delete("design");
    url.searchParams.set("site", id);
    window.history.replaceState(null, "", url);
  }, [id]);

  return {
    site,
    problem: pickProblem ?? pollProblem,
    // What a pick is opening, until it is answered or refused.
    opening: asking?.label ?? null,
    fromAddress: (addressId: number, address: string) =>
      pick(() => createSite(addressId), address),
    fromSection: (parcelId: number) =>
      pick(() => createSiteFromSection(parcelId), "the section you tapped"),
  };
}

/** Whether a failed pick is worth asking again: a failure that passes, but
 * not the daily cap's 429, which frees up in hours, not moments. */
function again(e: Error): boolean {
  return passing(e) && !(e instanceof ApiError && e.status === 429);
}

/** The site a link opens: `?site=`, or for a link to a design alone (as
 * links were before sites), that design's site; none for a plain page. */
function linkedSite(): (() => Promise<SiteState>) | null {
  if (typeof window === "undefined") return null;
  const query = new URLSearchParams(window.location.search);
  const site = query.get("site");
  if (site !== null) return () => getSite(site);
  const design = query.get("design");
  if (design === null) return null;
  return async () => {
    const job = await getDesign(design);
    if (job.siteId === null)
      throw new ApiError(`design ${design} doesn't say which site it is on`);
    return getSite(job.siteId);
  };
}
