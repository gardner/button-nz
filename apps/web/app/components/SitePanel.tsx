import type { Site } from "@/lib/api";
import { planView } from "@/lib/plan";

const MARGIN_M = 4;

/** The property: its title, a true-scale plan of its parcels, where every
 * piece of data came from, and what still needs confirming. */
export function SitePanel({ site }: { site: Site }) {
  const plan = planView(
    site.parcels.map((p) => p.ring),
    site.extent,
    MARGIN_M,
  );
  const [ax, ay] = plan.point(site.address);
  const bottom = Number(plan.viewBox.split(" ")[3]) - 1.5;
  return (
    <section className="flex flex-col gap-4">
      <header>
        <h2 className="text-xl font-semibold">{site.name}</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Record of title {site.title} · valuation {site.valuationNumber}
        </p>
      </header>
      <svg
        viewBox={plan.viewBox}
        className="w-full max-w-md rounded border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950"
        role="img"
        aria-label="Site plan, north up"
      >
        {plan.paths.map((d, i) => (
          <path
            key={site.parcels[i].id}
            d={d}
            className="parcel"
            fill="rgb(132 204 22 / 0.15)"
            stroke="rgb(220 38 38)"
            strokeWidth={0.25}
          />
        ))}
        <circle cx={ax} cy={ay} r={0.8} fill="rgb(37 99 235)" />
        <line
          x1={1}
          y1={bottom}
          x2={1 + plan.scaleBarM}
          y2={bottom}
          stroke="currentColor"
          strokeWidth={0.3}
        />
        <text x={1} y={bottom - 0.6} fontSize={1.4} fill="currentColor">
          {plan.scaleBarM} m · N ↑
        </text>
      </svg>
      <ul className="text-sm">
        {site.parcels.map((p) => (
          <li key={p.id}>{p.appellation}</li>
        ))}
      </ul>
      <div>
        <h3 className="font-medium">Sources</h3>
        <ul className="text-sm text-zinc-700 dark:text-zinc-300">
          {site.sources.map((s) => (
            <li key={s.key}>
              {s.title}: {s.licence}, {s.attribution}
              {s.capture &&
                `, captured ${s.capture.start.slice(0, 10)} to ${s.capture.end.slice(0, 10)}`}
            </li>
          ))}
        </ul>
      </div>
      {site.openItems.length > 0 && (
        <div>
          <h3 className="font-medium">Still to confirm</h3>
          <ul className="list-disc pl-5 text-sm">
            {site.openItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
