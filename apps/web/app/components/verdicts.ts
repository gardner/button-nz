import type { Attempt, Job } from "@/lib/api";

export const VERDICT_STYLE: Record<Attempt["status"], string> = {
  pass: "bg-green-100 text-green-900",
  unknown: "bg-amber-100 text-amber-900",
  fail: "bg-red-100 text-red-900",
  error: "bg-zinc-200 text-zinc-900",
};

/** The attempt the evaluator accepted, if there is one yet. */
export function acceptedAttempt(job: Job): Attempt | undefined {
  return job.attempts.find((a) => a.number === job.acceptedAttempt);
}

/** One word or two for how a design run ended (or that it hasn't): the
 * accepted attempt's verdict, "nothing accepted" or "failed". */
export function jobVerdict(job: Job): { label: string; style: string } {
  if (job.status === "failed") {
    return { label: "failed", style: VERDICT_STYLE.error };
  }
  if (job.status !== "done") {
    return { label: job.status, style: "bg-zinc-100 text-zinc-700" };
  }
  const accepted = acceptedAttempt(job);
  return accepted
    ? { label: accepted.status, style: VERDICT_STYLE[accepted.status] }
    : { label: "nothing accepted", style: VERDICT_STYLE.fail };
}
