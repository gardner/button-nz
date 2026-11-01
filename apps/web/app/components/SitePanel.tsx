import type { Aerial, Point, Site } from "@/lib/api";
import type { SiteFeature } from "@/lib/features";
import { interiorPoint, type PlanView, planView } from "@/lib/plan";

import { LOOKS, SHOWN } from "./decisions";

const MARGIN_M = 8; // enough to see what stands on the site's edges

/** The property: its title, a true-scale plan of its parcels and any
 * surveyed features, where every piece of data came from, and what still
 * needs confirming. */
export function SitePanel({
  site,
  features = [],
}: {
  site: Site;
  features?: SiteFeature[];
}) {
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
          Record of title {site.title}
          {site.valuationNumber && ` · valuation ${site.valuationNumber}`}
        </p>
      </header>
      <svg
        viewBox={plan.viewBox}
        className="w-full max-w-md rounded border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950"
        role="img"
        aria-label="Site plan, north up"
      >
        {site.aerial && <AerialPhoto aerial={site.aerial} plan={plan} />}
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
        {features.map((f) => (
          <FeatureShape key={f.id} feature={f} plan={plan} />
        ))}
        {features.map((f) => (
          <FeatureLabel key={f.id} feature={f} plan={plan} />
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
      {features.length > 0 && <PlanKey />}
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

/** The aerial photo, placed by its NZTM corners: the plan is in metres. */
function AerialPhoto({ aerial, plan }: { aerial: Aerial; plan: PlanView }) {
  const [west, south, east, north] = aerial.bbox;
  const [x, y] = plan.point([west, north]);
  return (
    <image
      href={aerial.url}
      x={x}
      y={y}
      width={east - west}
      height={north - south}
      preserveAspectRatio="none"
    />
  );
}

/** The feature's number, as in the list below, inside its largest piece. */
function FeatureLabel({
  feature,
  plan,
}: {
  feature: SiteFeature;
  plan: PlanView;
}) {
  const [largest] = [...feature.polygons].sort((a, b) => area(b) - area(a));
  if (!largest || largest.length === 0) return null;
  const middle = interiorPoint(largest);
  const [x, y] = plan.point(middle);
  return (
    <text
      x={x}
      y={y}
      className="feature-label"
      fontSize={2}
      fontWeight="bold"
      textAnchor="middle"
      dominantBaseline="middle"
      fill="white"
      stroke="black"
      strokeWidth={0.3}
      paintOrder="stroke"
    >
      {feature.id}
    </text>
  );
}

/** A surveyed feature, coloured by its decision; dashed until decided. */
function FeatureShape({
  feature,
  plan,
}: {
  feature: SiteFeature;
  plan: PlanView;
}) {
  const shown = feature.decision ?? "undecided";
  const { label, fill, stroke } = LOOKS[shown];
  return (
    <path
      d={plan.outline(feature.polygons.flat())}
      className="feature"
      data-decision={shown}
      fill={fill}
      fillRule="evenodd"
      stroke={stroke}
      strokeWidth={0.2}
      strokeDasharray={feature.decision ? undefined : "0.6 0.4"}
    >
      <title>{`#${feature.id} ${feature.concept}: ${label.toLowerCase()}`}</title>
    </path>
  );
}

function PlanKey() {
  return (
    <ul
      aria-label="Plan key"
      className="flex flex-wrap gap-x-4 gap-y-1 text-sm"
    >
      {SHOWN.map((shown) => (
        <li key={shown} className="flex items-center gap-1">
          <span
            aria-hidden
            className="inline-block h-3 w-3 border-2"
            style={{
              background: LOOKS[shown].fill,
              borderColor: LOOKS[shown].stroke,
              borderStyle: shown === "undecided" ? "dashed" : "solid",
            }}
          />
          {LOOKS[shown].label}
        </li>
      ))}
    </ul>
  );
}

/** A polygon's area (its outer ring less its holes), to pick the largest piece. */
function area(rings: Point[][]): number {
  const shoelace = (ring: Point[]) =>
    Math.abs(
      ring.reduce(
        (sum, [x, y], i) =>
          sum +
          (i + 1 < ring.length ? x * ring[i + 1][1] - ring[i + 1][0] * y : 0),
        0,
      ),
    ) / 2;
  const [outer, ...holes] = rings;
  return outer
    ? shoelace(outer) - holes.reduce((sum, h) => sum + shoelace(h), 0)
    : 0;
}
