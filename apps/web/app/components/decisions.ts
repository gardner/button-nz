import type { Decision } from "@/lib/features";

export type Shown = Decision | "undecided";

/** How a surveyed feature is named and drawn, by what a person decided it is.
 * Undecided ones are also dashed on the plan, so colour isn't the only cue. */
export const LOOKS: Record<
  Shown,
  { label: string; fill: string; stroke: string }
> = {
  building: {
    label: "Existing building",
    fill: "rgb(79 70 229 / 0.45)",
    stroke: "rgb(67 56 202)",
  },
  keep_clear: {
    label: "Keep clear",
    fill: "rgb(22 163 74 / 0.4)",
    stroke: "rgb(21 128 61)",
  },
  ignore: {
    label: "Ignore",
    fill: "rgb(161 161 170 / 0.2)",
    stroke: "rgb(161 161 170)",
  },
  undecided: {
    label: "Not decided yet",
    fill: "rgb(245 158 11 / 0.3)",
    stroke: "rgb(217 119 6)",
  },
};
