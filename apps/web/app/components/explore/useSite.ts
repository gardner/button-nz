"use client";

import { useEffect, useRef, useState } from "react";

import { passing } from "@/lib/fields";
import { type SiteState, createSite, getSite } from "@/lib/sites";

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
  // A site in the link is the first pick, asked for as the page opens.
  const [asking, setAsking] = useState<Asking | null>(() => {
    const linked =
      typeof window === "undefined"
        ? null
        : new URLSearchParams(window.location.search).get("site");
    return linked === null
      ? null
      : { request: () => getSite(linked), ask: 0, tries: 0, label: null };
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
              passing(e) ? { request, ask, tries: tries + 1, label } : null,
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
          setSite(state);
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
    // A design linked from another site isn't this site's.
    if (url.searchParams.get("site") !== id) url.searchParams.delete("design");
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
  };
}
