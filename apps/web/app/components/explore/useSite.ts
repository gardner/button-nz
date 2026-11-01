"use client";

import { useEffect, useRef, useState } from "react";

import { passing } from "@/lib/fields";
import { type SiteState, createSite, getSite } from "@/lib/sites";

/** The site being explored: started from an address or a clicked section,
 * followed while the server builds it, and kept in the address bar
 * (`?site=<id>`) so the page can be shared and reopened. A poll that fails
 * for a moment (a 502 while the API restarts, a timeout) is retried; one the
 * API refuses for good stops the following, with its reason shown. */
export function useSite(pollMs: number) {
  const [site, setSite] = useState<SiteState | null>(null);
  // Why a pick failed stays until the next pick; why a poll failed, until
  // the next poll answers. A poll can't clear a pick's reason.
  const [pickProblem, setPickProblem] = useState<string | null>(null);
  const [pollProblem, setPollProblem] = useState<string | null>(null);
  const [retries, setRetries] = useState(0);
  // The newest site asked for. Only a person's pick moves it on; a poll
  // checks it, so a late answer about an older site never replaces a newer one.
  const picked = useRef(0);

  /** A new pick starts with no reason left over from the last one. */
  function forget() {
    setPickProblem(null);
    setPollProblem(null);
  }

  function pick(
    request: () => Promise<SiteState>,
    onFailure?: (e: Error) => void,
  ) {
    const ask = ++picked.current;
    request().then(
      (state) => {
        if (ask !== picked.current) return;
        setPickProblem(null);
        setPollProblem(null);
        setSite(state);
      },
      (e: Error) => {
        if (ask !== picked.current) return;
        setPickProblem(e.message);
        setRetries((n) => n + 1); // keep following the site still on show
        onFailure?.(e);
      },
    );
  }

  // A site opened from a link, asked for again after a failure that passes.
  // A pick of the person's own stops it: only the newest ask can fail.
  const [linked] = useState(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("site"),
  );
  const [linkTries, setLinkTries] = useState(0);
  useEffect(() => {
    if (linked === null) return;
    const ask = picked.current;
    const timer = setTimeout(
      () => {
        if (ask !== picked.current) return; // the person has picked since
        pick(
          () => getSite(linked),
          (e) => passing(e) && setLinkTries((n) => n + 1),
        );
      },
      linkTries === 0 ? 0 : pollMs,
    );
    return () => clearTimeout(timer);
  }, [linked, linkTries]); // eslint-disable-line react-hooks/exhaustive-deps -- pollMs only paces

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
    url.searchParams.set("site", id);
    window.history.replaceState(null, "", url);
  }, [id]);

  return {
    site,
    problem: pickProblem ?? pollProblem,
    fromAddress: (addressId: number) => {
      forget();
      pick(() => createSite(addressId));
    },
  };
}
