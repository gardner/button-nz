export type Step = "find" | "survey" | "design" | "check" | "prefab";

const STEPS: { key: Step; label: string }[] = [
  { key: "find", label: "Find" },
  { key: "survey", label: "Survey" },
  { key: "design", label: "Design" },
  { key: "check", label: "Check" },
  { key: "prefab", label: "Prefab" },
];

export interface JourneyState {
  site?: "building" | "ready" | "failed" | "no_lidar";
  design?: "queued" | "running" | "accepted" | "failed";
  prefabs?: boolean; // the owner has asked which prefabs fit
}

/** Where the journey has got to, from what is really on the page. */
export function stepOf({ site, design, prefabs }: JourneyState): Step {
  if (site !== "ready") return "find";
  if (design === undefined) return "survey";
  if (design === "queued" || design === "running") return "design";
  return design === "accepted" && prefabs ? "prefab" : "check";
}

/** Find → Survey → Design → Check → Prefab, with the step on now marked. */
export function Stepper({ current }: { current: Step }) {
  const at = STEPS.findIndex((s) => s.key === current);
  return (
    <ol
      aria-label="Progress"
      className="flex items-center gap-1 rounded-full bg-zinc-950/70 p-1 text-sm text-white shadow-lg backdrop-blur"
    >
      {STEPS.map((step, i) => {
        const state = i < at ? "done" : i === at ? "now" : "todo";
        return (
          <li
            key={step.key}
            data-state={state}
            aria-current={state === "now" ? "step" : undefined}
            className={`flex items-center gap-2 rounded-full px-2 py-1.5 transition sm:px-3 ${
              state === "now"
                ? "bg-emerald-500 font-semibold text-zinc-950"
                : state === "done"
                  ? "text-emerald-300"
                  : "text-zinc-400"
            }`}
          >
            <span
              aria-hidden
              className={`flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                state === "now"
                  ? "bg-zinc-950 text-emerald-400"
                  : "border border-current"
              }`}
            >
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className={state === "now" ? "" : "hidden sm:inline"}>
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
