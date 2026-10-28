"use client";

import { useEffect, useState } from "react";

import { type Site, getSite } from "@/lib/api";
import type { SiteFeature } from "@/lib/features";

import { FeaturesPanel } from "./FeaturesPanel";
import { SitePanel } from "./SitePanel";
import { useSurvey } from "./useSurvey";

/** The site from the API (loading, the panel, or why it couldn't be read),
 * with the surveyed features drawn on its plan and listed for a person to
 * confirm. Either can fail without hiding the other. */
export function SiteSection() {
  const survey = useSurvey();
  return (
    <div className="flex flex-col gap-8">
      <SiteView features={survey.survey?.features ?? []} />
      <FeaturesPanel {...survey} />
    </div>
  );
}

function SiteView({ features }: { features: SiteFeature[] }) {
  const [site, setSite] = useState<Site | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    getSite().then(setSite, (e: Error) => setProblem(e.message));
  }, []);
  if (problem)
    return <p className="text-red-700">Could not load the site: {problem}</p>;
  if (!site) return <p className="text-zinc-600">Loading the site…</p>;
  return <SitePanel site={site} features={features} />;
}
