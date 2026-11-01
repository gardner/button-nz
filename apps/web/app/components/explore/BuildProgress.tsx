import type { SiteStatus, SiteStep } from "@/lib/sites";

const STEPS: { key: SiteStep; doing: string }[] = [
  { key: "parcels", doing: "Finding the title's parcels" },
  { key: "terrain", doing: "Reading the LiDAR" },
  { key: "aerial", doing: "Fetching the aerial photo" },
  { key: "survey", doing: "SAM 3.1 is surveying the site" },
];

/** A site being built from LINZ's open data, step by step, or why it can't be. */
export function BuildProgress({
  address,
  status,
  step,
  error,
}: {
  address: string;
  status: SiteStatus;
  step: SiteStep | null;
  error: string | null;
}) {
  if (status === "no_lidar" || status === "failed") {
    return (
      <div
        role="alert"
        className="rounded-2xl bg-zinc-950/85 p-5 text-white shadow-2xl backdrop-blur"
      >
        <p className="text-sm text-zinc-400">{address}</p>
        <p className="mt-1 text-lg font-semibold">
          {status === "no_lidar"
            ? "No LiDAR here yet"
            : "Couldn't build this site"}
        </p>
        {error && <p className="mt-1 text-sm text-zinc-300">{error}</p>}
      </div>
    );
  }
  const at = STEPS.findIndex((s) => s.key === step);
  return (
    <div className="rounded-2xl bg-zinc-950/85 p-5 text-white shadow-2xl backdrop-blur">
      <p className="text-lg font-semibold">{address}</p>
      <p role="status" className="sr-only">
        {at >= 0 ? `${STEPS[at].doing}…` : "Starting…"}
      </p>
      <ol className="mt-3 flex flex-col gap-2 text-sm">
        {STEPS.map((s, i) => (
          <li key={s.key} className="flex items-center gap-3">
            <span
              aria-hidden
              className={`flex h-5 w-5 items-center justify-center rounded-full text-xs ${
                i < at
                  ? "bg-emerald-500 text-zinc-950"
                  : i === at
                    ? "animate-pulse bg-emerald-400/30 ring-2 ring-emerald-400"
                    : "border border-zinc-600"
              }`}
            >
              {i < at ? "✓" : ""}
            </span>
            <span
              className={
                i === at
                  ? "text-white"
                  : i < at
                    ? "text-zinc-400"
                    : "text-zinc-500"
              }
            >
              {s.doing}
              {i === at ? "…" : ""}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
