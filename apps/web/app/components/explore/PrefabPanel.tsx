"use client";

import { useEffect, useRef, useState } from "react";

import { getProducts } from "@/lib/api";
import type { Product, Products } from "@/lib/products";

import { NextSteps } from "./NextSteps";

const PRICE = new Intl.NumberFormat("en-NZ", {
  style: "currency",
  currency: "NZD",
  maximumFractionDigits: 0,
});

/** The real prefabs that fit inside the accepted design's walls, found when
 * asked: each with its price, size and rooms, shown on the map while pointed
 * at (`onHover`), and placed on the site in one click (`onPlace`). */
export function PrefabPanel({
  jobId,
  busy,
  onPlace,
  onHover,
  onShown,
}: {
  jobId: string;
  busy: boolean;
  onPlace: (product: Product) => void;
  onHover: (product: Product | null) => void;
  /** Whether the list is on the page: true once it is, false when it goes. */
  onShown: (shown: boolean) => void;
}) {
  const [found, setFound] = useState<Products | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const shown = useRef(onShown);
  useEffect(() => {
    shown.current = onShown; // the newest, for the unmount below
  });
  useEffect(() => () => shown.current(false), []);
  // From state, which a reply after unmount can't set: a late reply can't
  // report a list that isn't on the page.
  useEffect(() => {
    if (found) shown.current(true);
  }, [found]);

  function ask() {
    setAsking(true);
    setProblem(null);
    getProducts(jobId)
      .then(setFound, (e: Error) => setProblem(e.message))
      .finally(() => setAsking(false));
  }

  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-zinc-950/85 p-5 shadow-2xl backdrop-blur">
      {!found && (
        <button
          type="button"
          onClick={ask}
          disabled={asking}
          className="rounded-xl bg-white px-4 py-2 font-semibold text-zinc-950 shadow-lg disabled:opacity-50"
        >
          Which real prefabs fit?
        </button>
      )}
      {problem && (
        <p role="alert" className="text-sm text-red-300">
          Couldn&apos;t find prefabs: {problem}
        </p>
      )}
      {found && (
        <Found found={found} busy={busy} onPlace={onPlace} onHover={onHover} />
      )}
    </section>
  );
}

function Found({
  found,
  busy,
  onPlace,
  onHover,
}: {
  found: Products;
  busy: boolean;
  onPlace: (product: Product) => void;
  onHover: (product: Product | null) => void;
}) {
  return (
    <>
      <h2 className="text-lg font-semibold">
        {found.fits.length === 0
          ? `No checked prefab fits these ${found.footprintM2} m² walls`
          : `${found.fits.length} real prefab${found.fits.length === 1 ? "" : "s"} fit`}
      </h2>
      <div className="flex flex-col gap-2">
        {found.fits.map((p) => (
          <PrefabCard
            key={p.id}
            product={p}
            busy={busy}
            onPlace={onPlace}
            onHover={onHover}
          />
        ))}
      </div>
      {found.unchecked.length > 0 && (
        <p className="text-xs text-zinc-400">
          Not checked (dimensions not labelled):{" "}
          {found.unchecked.map((p) => `${p.supplier} ${p.model}`).join(", ")}
        </p>
      )}
      <p className="text-xs text-zinc-500">{found.basis}</p>
      <NextSteps />
    </>
  );
}

function PrefabCard({
  product: p,
  busy,
  onPlace,
  onHover,
}: {
  product: Product;
  busy: boolean;
  onPlace: (product: Product) => void;
  onHover: (product: Product | null) => void;
}) {
  const name = `${p.supplier} ${p.model}`;
  return (
    <article
      onMouseEnter={() => onHover(p)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(p)}
      onBlur={() => onHover(null)}
      className="flex flex-col gap-1 rounded-xl bg-white/5 p-3 transition hover:bg-white/10"
    >
      <div className="flex items-baseline justify-between gap-2">
        <a
          href={p.url}
          target="_blank"
          rel="noreferrer"
          className="font-semibold hover:underline"
        >
          {name}
        </a>
        <span className="text-lg font-semibold text-emerald-300">
          {p.priceNzd === null
            ? "Price not published"
            : PRICE.format(p.priceNzd)}
        </span>
      </div>
      <p className="text-sm text-zinc-300">
        {p.lengthM} × {p.widthM} m · {p.floorAreaM2} m² ({p.areaBasis}) ·{" "}
        {p.bedrooms} bed, {p.bathrooms} bath
      </p>
      <p className="text-xs text-zinc-500">
        {p.priceBasis}. Excludes {p.excludes}.
      </p>
      <p className="text-xs text-zinc-500">West Coast: {p.westCoast}</p>
      {p.placeable ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onPlace(p)}
          aria-label={`Place the ${name} on the site`}
          className="mt-1 self-start rounded-lg bg-emerald-400 px-3 py-1 text-sm font-semibold text-zinc-950 disabled:opacity-40"
        >
          Place it on the site
        </button>
      ) : (
        <p className="text-xs text-zinc-500">
          Can&apos;t be placed: its plan isn&apos;t the rectangle its figures
          give.
        </p>
      )}
    </article>
  );
}
