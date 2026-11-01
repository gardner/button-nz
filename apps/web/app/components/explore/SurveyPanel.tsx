"use client";

import { DECISIONS, type SiteFeature, type Survey } from "@/lib/features";

import { LOOKS } from "../decisions";
import type { SurveyControl } from "../useSurvey";

/** What SAM 3.1 found on the site, as chips to pick, the picked one (from a
 * chip or the map) with its three choices, and the buildings-listed switch.
 * A survey the server has fixed shows its decisions without the controls. */
export function SurveyPanel({
  control,
  selected,
  onSelect,
  compact = false,
  onEdit,
}: {
  control: SurveyControl;
  selected: string | null;
  onSelect: (id: string) => void;
  /** Folded to a summary, as it is while a design is on show. */
  compact?: boolean;
  onEdit?: () => void;
}) {
  const { survey, missing, failed } = control;
  if (missing) return <Note>{missing}</Note>;
  if (failed) return <Note>Couldn&apos;t read the survey: {failed}</Note>;
  if (!survey) return <Note>Reading the survey…</Note>;
  if (compact) return <Summary features={survey.features} onEdit={onEdit} />;
  return (
    <OpenSurvey
      control={control}
      survey={survey}
      selected={selected}
      onSelect={onSelect}
    />
  );
}

function OpenSurvey({
  control,
  survey,
  selected,
  onSelect,
}: {
  control: SurveyControl;
  survey: Survey;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { refused, saving, decide, setComplete } = control;
  const fixed = survey.decidedBy !== null;
  const picked = survey.features.find((f) => f.id === selected);
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-zinc-950/85 p-5 shadow-2xl backdrop-blur">
      <header>
        <h2 className="text-lg font-semibold">What&apos;s on the site?</h2>
        <p className="text-sm text-zinc-400">
          {fixed
            ? `Fixed on this server, as ${survey.decidedBy} decided it.`
            : "Tap a shape on the map, or a chip, and say what it is."}
        </p>
      </header>
      <Chips
        features={survey.features}
        selected={selected}
        onSelect={onSelect}
      />
      {picked && (
        <PickedFeature
          feature={picked}
          disabled={saving || fixed}
          onDecide={decide}
        />
      )}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={survey.buildingsComplete}
          disabled={saving || fixed}
          onChange={(e) => setComplete(e.target.checked)}
        />
        Every building on the site is listed
      </label>
      {refused && (
        <p role="alert" className="text-sm text-red-300">
          Not saved: {refused}
        </p>
      )}
    </section>
  );
}

/** Each feature found, as a chip with its decision; one picks it. */
function Chips({
  features,
  selected,
  onSelect,
}: {
  features: SiteFeature[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="flex flex-wrap gap-2">
      {features.map((f) => (
        <li key={f.id}>
          <button
            type="button"
            onClick={() => onSelect(f.id)}
            aria-pressed={f.id === selected}
            className={`rounded-full border px-3 py-1 text-sm ${
              f.id === selected
                ? "border-yellow-300 bg-yellow-300/20"
                : "border-white/20 hover:bg-white/10"
            }`}
          >
            <span className="font-medium">
              #{f.id} {f.concept}
            </span>{" "}
            <span className="text-zinc-400">· {label(f)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The feature picked, from a chip or the map, and its three choices. */
function PickedFeature({
  feature,
  disabled,
  onDecide,
}: {
  feature: SiteFeature;
  disabled: boolean;
  onDecide: SurveyControl["decide"];
}) {
  return (
    <div
      role="group"
      aria-label={`What is #${feature.id} ${feature.concept}?`}
      className="flex flex-col gap-2 rounded-xl bg-white/5 p-3"
    >
      <p className="text-sm text-zinc-300">
        #{feature.id} {feature.concept}: {feature.areaM2.toFixed(0)} m²
        {feature.maxHeightM !== null &&
          `, up to ${feature.maxHeightM.toFixed(1)} m tall`}
      </p>
      <div className="flex flex-wrap gap-2">
        {DECISIONS.map((decision) => (
          <button
            key={decision}
            type="button"
            disabled={disabled}
            aria-pressed={feature.decision === decision}
            onClick={() => onDecide(feature.id, decision)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${
              feature.decision === decision
                ? "bg-emerald-400 text-zinc-950"
                : "bg-white/10 hover:bg-white/20"
            }`}
          >
            {LOOKS[decision].label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The survey in one line, with a way back to it. */
function Summary({
  features,
  onEdit,
}: {
  features: SiteFeature[];
  onEdit?: () => void;
}) {
  const count = (d: SiteFeature["decision"]) =>
    features.filter((f) => f.decision === d).length;
  const buildings = count("building");
  return (
    <section className="flex items-center justify-between gap-3 rounded-2xl bg-zinc-950/85 px-5 py-3 text-sm shadow-2xl backdrop-blur">
      <p>
        <span className="font-semibold">Survey:</span> {buildings} building
        {buildings === 1 ? "" : "s"} · {count("keep_clear")} kept clear ·{" "}
        {count(null)} undecided
      </p>
      {onEdit && (
        <button
          type="button"
          onClick={onEdit}
          className="rounded-lg bg-white/10 px-3 py-1 hover:bg-white/20"
        >
          Edit
        </button>
      )}
    </section>
  );
}

function label(feature: SiteFeature): string {
  if (!feature.decision) return "Undecided";
  const named = LOOKS[feature.decision].label;
  return feature.suggested ? `${named} (suggested)` : named;
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-2xl bg-zinc-950/85 p-4 text-sm text-zinc-300">
      {children}
    </p>
  );
}
