import { useId } from "react";

import {
  DECISIONS,
  type FeatureStatus,
  type SiteFeature,
  type Survey,
} from "@/lib/features";

import { LOOKS } from "./decisions";
import type { SurveyControl } from "./useSurvey";

const STATUS: Record<FeatureStatus, { label: string; style: string }> = {
  agrees: { label: "LiDAR agrees", style: "bg-green-100 text-green-900" },
  conflict: { label: "LiDAR disagrees", style: "bg-red-100 text-red-900" },
  transient: {
    label: "Probably temporary",
    style: "bg-zinc-200 text-zinc-900",
  },
  unchecked: {
    label: "Not checked against the LiDAR",
    style: "bg-zinc-200 text-zinc-900",
  },
  unlabelled: {
    label: "Only the LiDAR saw it",
    style: "bg-amber-100 text-amber-900",
  },
};

// The label and the LiDAR disagree, or nothing labelled it: a person decides.
const DOUBTFUL: readonly FeatureStatus[] = ["conflict", "unlabelled"];

/** What the survey found on the site, for a person to say what each thing is:
 * designs keep their distance from existing buildings and build nothing on
 * what is kept clear. */
export function FeaturesPanel(control: SurveyControl) {
  return (
    <section className="flex flex-col gap-4">
      <header>
        <h2 className="text-xl font-semibold">What is on the site</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Found on the aerial photo by an AI model and checked against the
          LiDAR. Say what each one is: new designs keep their distance from
          existing buildings and build nothing on what is kept clear.
        </p>
      </header>
      <SurveyBody {...control} />
    </section>
  );
}

function SurveyBody({ survey, missing, failed, ...control }: SurveyControl) {
  if (missing) return <p className="text-zinc-600">{missing}</p>;
  if (failed)
    return <p className="text-red-700">Could not load the survey: {failed}</p>;
  if (!survey) return <p className="text-zinc-600">Loading the survey…</p>;
  return <SurveyList survey={survey} {...control} />;
}

function SurveyList({
  survey,
  refused,
  saving,
  decide,
  setComplete,
}: Omit<SurveyControl, "survey" | "missing" | "failed"> & { survey: Survey }) {
  const locked = saving || survey.decidedBy !== null;
  return (
    <>
      {survey.decidedBy !== null && (
        <p className="text-sm font-medium">
          This survey is fixed on this server, as {survey.decidedBy} decided it.
        </p>
      )}
      {survey.features.length === 0 ? (
        <p className="text-zinc-600">The survey found nothing on the site.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {survey.features.map((f) => (
            <FeatureCard
              key={f.id}
              feature={f}
              disabled={locked}
              onDecide={decide}
            />
          ))}
        </ul>
      )}
      <div>
        <label className="flex items-center gap-2 font-medium">
          <input
            type="checkbox"
            checked={survey.buildingsComplete}
            disabled={locked}
            onChange={(e) => setComplete(e.target.checked)}
          />
          Every building on the site is listed
        </label>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Until this is ticked, a design&apos;s distance from existing buildings
          can&apos;t be checked: one might be missing.
        </p>
      </div>
      {refused && (
        <p role="alert" className="text-red-700">
          Not saved: {refused}
        </p>
      )}
    </>
  );
}

function FeatureCard({
  feature,
  disabled,
  onDecide,
}: {
  feature: SiteFeature;
  disabled: boolean; // a change is being saved, or the survey is fixed
  onDecide: SurveyControl["decide"];
}) {
  const heading = useId();
  const name = `#${feature.id} ${feature.concept}`;
  const doubtful = DOUBTFUL.includes(feature.status);
  const status = STATUS[feature.status];
  return (
    <li>
      <article
        aria-labelledby={heading}
        className={`flex flex-col gap-2 rounded border p-3 ${doubtful ? "border-amber-500" : "border-zinc-200 dark:border-zinc-800"}`}
      >
        <header className="flex flex-wrap items-center gap-2">
          <h3 id={heading} className="font-medium">
            {name}
          </h3>
          <span className={`rounded px-2 text-sm ${status.style}`}>
            {status.label}
          </span>
          {doubtful && (
            <span className="rounded bg-amber-500 px-2 text-sm font-medium text-white">
              Needs your judgement
            </span>
          )}
        </header>
        <p className="text-sm">{measured(feature)}</p>
        <p className="text-sm text-zinc-700 dark:text-zinc-300">
          {feature.note}
        </p>
        <div
          role="group"
          aria-label={`What is ${name}?`}
          className="flex flex-wrap gap-2"
        >
          {DECISIONS.map((decision) => (
            <DecisionButton
              key={decision}
              label={LOOKS[decision].label}
              pressed={feature.decision === decision}
              disabled={disabled}
              onClick={() => onDecide(feature.id, decision)}
            />
          ))}
        </div>
      </article>
    </li>
  );
}

function DecisionButton({
  label,
  pressed,
  disabled,
  onClick,
}: {
  label: string;
  pressed: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const look = pressed
    ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
    : "border-zinc-300 dark:border-zinc-700";
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={`rounded border px-3 py-1 text-sm disabled:opacity-60 ${look}`}
    >
      {label}
    </button>
  );
}

function measured({ areaM2, maxHeightM }: SiteFeature): string {
  const height =
    maxHeightM === null
      ? "no height from the LiDAR"
      : `up to ${maxHeightM.toFixed(1)} m tall`;
  return `${areaM2.toFixed(1)} m² · ${height}`;
}
