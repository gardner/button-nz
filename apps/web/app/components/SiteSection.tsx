"use client";

import { useEffect, useState } from "react";

import { type Site, getSite } from "@/lib/api";

import { SitePanel } from "./SitePanel";

/** The site from the API: loading, the panel, or why it couldn't be read. */
export function SiteSection() {
  const [site, setSite] = useState<Site | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    getSite().then(setSite, (e: Error) => setProblem(e.message));
  }, []);
  if (problem)
    return <p className="text-red-700">Could not load the site: {problem}</p>;
  if (!site) return <p className="text-zinc-600">Loading the site…</p>;
  return <SitePanel site={site} />;
}
