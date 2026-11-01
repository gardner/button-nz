import type { FeatureCollection } from "@/lib/geo";
import type { TownCategory, TownSection } from "@/lib/sites";

/** How each section is filled on the town map. */
export const TOWN_COLOURS: Record<TownCategory, string> = {
  clear: "#10b981",
  outlines: "#f59e0b",
  none: "#a1a1aa",
};

const KEY: { category: TownCategory; label: string }[] = [
  { category: "clear", label: "Room today, clear of trees and sheds" },
  { category: "outlines", label: "Room on the building outlines" },
  { category: "none", label: "No room for a prefab" },
];

const COUNT = new Intl.NumberFormat("en-NZ");

/** The town screen's headline, counted from the sections on the map, and
 * the key to their colours. */
export function TownOverview({
  town,
  name,
}: {
  town: FeatureCollection<TownSection>;
  name: string;
}) {
  const total = town.features.length;
  const room = town.features.filter(
    (f) => f.properties.category !== "none",
  ).length;
  return (
    <section className="rounded-2xl bg-zinc-950/80 p-5 text-white shadow-2xl backdrop-blur">
      <p className="text-3xl font-semibold leading-tight">
        <span className="text-emerald-400">{COUNT.format(room)}</span> of {name}
        &apos;s {COUNT.format(total)} sections have room for a real prefab
      </p>
      <p className="mt-2 text-sm text-zinc-400">
        Each checked 2 m from its boundaries and buildings, with 0.6 m eaves.
        Find yours by its address.
      </p>
      <ul aria-label="Map key" className="mt-4 flex flex-col gap-1.5 text-sm">
        {KEY.map(({ category, label }) => (
          <li key={category} className="flex items-center gap-2">
            <span
              aria-hidden
              className="h-3.5 w-3.5 rounded-sm"
              style={{ backgroundColor: TOWN_COLOURS[category] }}
            />
            {label}
          </li>
        ))}
      </ul>
    </section>
  );
}
