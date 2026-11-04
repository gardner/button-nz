"use client";

import { useEffect, useState } from "react";

import { getCatalogue } from "@/lib/api";
import { type SketchScale, sketch, sketchScale } from "@/lib/prefabSketch";
import type { Product } from "@/lib/products";

const NZD = new Intl.NumberFormat("en-NZ", {
  style: "currency",
  currency: "NZD",
  maximumFractionDigits: 0,
});

/** While a design is made: the real prefab catalogue to browse, each with
 * our own sketch of it, its size (where published as a footprint), bedrooms
 * and published price, and the supplier's own page. The suppliers' photos
 * are theirs, not ours to show. */
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
  const scale = sketchScale(products);
  return (
    <section aria-label="Prefabs to browse" className="flex flex-col gap-2">
      <h3 className="text-sm font-medium text-zinc-300">
        Meanwhile: real New Zealand prefabs
      </h3>
      <p className="text-xs text-zinc-500">
        Our sketches, from the published sizes, to one scale; the wall height,
        and the colours and pitch where not published, are illustrative.
      </p>
      <ul className="flex max-h-64 flex-col gap-1.5 overflow-y-auto pr-1 text-sm">
        {products.map((p) => (
          <li
            key={p.id}
            className="flex items-center gap-3 rounded-lg bg-white/5 px-2 py-1.5"
          >
            <Sketch product={p} scale={scale} />
            {/* One column beside the sketch, its price under its name, so a
                long price basis wraps rather than widening the panel. */}
            <div className="min-w-0 flex-1">
              <p>
                <a
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium hover:underline"
                >
                  {p.model}
                </a>{" "}
                <span className="text-zinc-400">
                  · {p.supplier} · {sizeOf(p)} · {p.bedrooms} bed
                </span>
              </p>
              <p className="text-zinc-300">
                <span className="tabular-nums">
                  {p.priceNzd === null
                    ? "price not published"
                    : NZD.format(p.priceNzd)}
                </span>
                {p.priceNzd !== null && (
                  <span className="text-xs text-zinc-500">
                    {" "}
                    · {p.priceBasis}
                  </span>
                )}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Our sketch of `product`, or an empty tile saying why there is none. */
function Sketch({ product, scale }: { product: Product; scale: SketchScale }) {
  const drawn = sketch(product, scale);
  const label =
    "faces" in drawn
      ? drawn.description
      : `No sketch of the ${product.model}: ${drawn.missing}`;
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${scale.width} ${scale.height}`}
      width={scale.width}
      height={scale.height}
      className={`shrink-0 rounded-md bg-zinc-900/70 ${
        "faces" in drawn ? "" : "ring-1 ring-white/10 ring-inset"
      }`}
    >
      <title>{label}</title>
      {"faces" in drawn &&
        drawn.faces.map((face, i) => (
          <polygon
            key={i}
            points={face.points.map((p) => p.join(",")).join(" ")}
            fill={face.fill}
            stroke="#18181b"
            strokeWidth={0.5}
            strokeLinejoin="round"
          />
        ))}
    </svg>
  );
}

/** Its outside footprint, where the supplier's figures are one: labelled,
 * and a rectangle rather than the box round a stepped plan (`placeable`). */
function sizeOf(p: Product): string {
  return p.placeable
    ? `${p.lengthM} × ${p.widthM} m`
    : "size not published as a footprint";
}
