"use client";

import { useEffect, useState } from "react";

import { getCatalogue } from "@/lib/api";
import type { Product } from "@/lib/products";

const NZD = new Intl.NumberFormat("en-NZ", {
  style: "currency",
  currency: "NZD",
  maximumFractionDigits: 0,
});

/** While a design is made: the real prefab catalogue to browse, each with
 * its size, bedrooms and published price, and the supplier's own page. Only
 * words and figures: the suppliers' photos are theirs, not ours to show. */
export function PrefabsMeanwhile() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    let gone = false;
    getCatalogue().then(
      (found) => !gone && setProducts(found),
      (e: Error) => !gone && setProblem(e.message),
    );
    return () => {
      gone = true;
    };
  }, []);
  if (problem)
    return (
      <p className="text-sm text-zinc-400">
        Couldn&apos;t load the prefabs: {problem}
      </p>
    );
  if (!products) return null;
  return (
    <section aria-label="Prefabs to browse" className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-300">
        Meanwhile: real New Zealand prefabs
      </h3>
      <ul className="flex max-h-48 flex-col gap-1.5 overflow-y-auto pr-1 text-sm">
        {products.map((p) => (
          <li
            key={p.id}
            className="flex items-baseline justify-between gap-2 rounded-lg bg-white/5 px-3 py-1.5"
          >
            <span>
              <a
                href={p.url}
                target="_blank"
                rel="noreferrer"
                className="font-medium hover:underline"
              >
                {p.model}
              </a>{" "}
              <span className="text-zinc-400">
                · {p.supplier} · {p.lengthM} × {p.widthM} m · {p.bedrooms} bed
              </span>
            </span>
            <span className="shrink-0 tabular-nums text-zinc-300">
              {p.priceNzd === null
                ? "price on request"
                : NZD.format(p.priceNzd)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
