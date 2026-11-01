import { useEffect, useState } from "react";

import {
  ApiError,
  decideFeature,
  getFeatures,
  setBuildingsComplete,
} from "@/lib/api";
import type { Decision, Survey } from "@/lib/features";

export interface SurveyControl {
  survey: Survey | null;
  missing: string | null; // there is no survey yet, in the API's words
  failed: string | null; // the survey couldn't be read
  refused: string | null; // the last change wasn't saved, and why
  saving: boolean;
  decide: (id: string, decision: Decision) => void;
  setComplete: (complete: boolean) => void;
}

/** The site survey from the API, and the person's decisions about it. One
 * change is saved at a time, so responses can't arrive out of order. With
 * `siteId`, the survey is that site's (else the demo site's); `onSaved`
 * hears each change saved (the site's map redraws what it constrains). */
export function useSurvey(
  siteId?: string,
  onSaved?: () => void,
): SurveyControl {
  const [survey, setSurvey] = useState<Survey | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    getFeatures(siteId).then(setSurvey, (e: Error) => {
      if (e instanceof ApiError && e.status === 404) setMissing(e.message);
      else setFailed(e.message);
    });
  }, [siteId]);

  // Each change names the survey it was made on, so one made on a survey
  // replaced since the page loaded is refused rather than misapplied.
  function save<T>(
    change: (surveyId: string) => Promise<T>,
    apply: (s: Survey, r: T) => Survey,
  ) {
    if (survey === null) return;
    setSaving(true);
    change(survey.id)
      .then(
        (result) => {
          setRefused(null);
          setSurvey((s) => s && apply(s, result));
          onSaved?.();
        },
        (e: Error) => setRefused(e.message),
      )
      .finally(() => setSaving(false));
  }

  return {
    survey,
    missing,
    failed,
    refused,
    saving,
    decide: (id, decision) =>
      save(
        (surveyId) => decideFeature(surveyId, id, decision, siteId),
        (s, decided) => ({
          ...s,
          features: s.features.map((f) => (f.id === decided.id ? decided : f)),
        }),
      ),
    setComplete: (complete) =>
      save(
        (surveyId) => setBuildingsComplete(surveyId, complete, siteId),
        (s, buildingsComplete) => ({ ...s, buildingsComplete }),
      ),
  };
}
