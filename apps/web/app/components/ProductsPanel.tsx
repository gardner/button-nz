"use client";

import { useState } from "react";

import { getProducts } from "@/lib/api";
import type { Product, Products } from "@/lib/products";

const PRICE = new Intl.NumberFormat("en-NZ", {
  style: "currency",
  currency: "NZD",
  maximumFractionDigits: 0,
});

/** The real prefab homes that fit inside an accepted design's walls, as their
 * suppliers publish them, found when the owner asks. Each can be placed on the
 * site (`onPlace`): designed again to its footprint, once no design is running. */
export function ProductsPanel({
  jobId,
  busy,
  onPlace,
}: {
  jobId: string;
  busy: boolean;
  onPlace: (product: Product) => void;
}) {
  const [products, setProducts] = useState<Products | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  async function ask() {
    setAsking(true);
    setProblem(null);
    try {
      setProducts(await getProducts(jobId));
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    } finally {
      setAsking(false);
    }
  }

  return (
    <section className="flex flex-col gap-2">
      <button
        type="button"
        onClick={ask}
        disabled={asking}
        className="self-start rounded border border-zinc-300 px-3 py-1 disabled:opacity-40 dark:border-zinc-700"
      >
        Which real prefabs fit?
      </button>
      {problem && (
        <p className="text-red-700">Could not find products: {problem}</p>
      )}
      {products && <Found products={products} busy={busy} onPlace={onPlace} />}
    </section>
  );
}

function Found({
  products,
  busy,
  onPlace,
}: {
  products: Products;
  busy: boolean;
  onPlace: (product: Product) => void;
}) {
  const { fits, unchecked, footprintM2, basis } = products;
  return (
    <>
      {fits.length === 0 ? (
        <p>No checked product fits inside these {footprintM2} m² walls.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {fits.map((p) => (
            <ProductCard key={p.id} product={p} busy={busy} onPlace={onPlace} />
          ))}
        </ul>
      )}
      {unchecked.length > 0 && (
        <p className="text-sm">
          Not checked (dimensions not labelled):{" "}
          {unchecked.map((p) => `${p.supplier} ${p.model}`).join(", ")}
        </p>
      )}
      <p className="text-xs text-zinc-600 dark:text-zinc-400">{basis}</p>
      <NextSteps />
    </>
  );
}

const BDC =
  "https://bullerdc.govt.nz/property-rates-and-building/building-and-building-consents/granny-flat-building-consent-exemption/";
const SUPPLIERS =
  "https://github.com/gardner/button-nz/blob/master/docs/suppliers.md";

/** What the granny-flat exemption asks of the owner next, from the council's
 * page and the sourced research on who serves Reefton. */
export function NextSteps() {
  return (
    <section className="flex flex-col gap-1 text-sm">
      <h3 className="font-medium">Next steps</h3>
      <ol className="list-decimal pl-5">
        <li>
          A project information memorandum (PIM) from{" "}
          <a href={BDC} target="_blank" rel="noreferrer" className="underline">
            Buller District Council
          </a>{" "}
          before work starts.
        </li>
        <li>
          A licensed designer to design it, and a licensed building practitioner
          to build or supervise it.
        </li>
        <li>
          A ground test before choosing foundations; poor ground needs a
          geotechnical investigation and an engineer.
        </li>
        <li>
          Certifying plumbers, drainlayers and electricians, who give you their
          records; within 20 working days of completion you give the council the
          final plans and every record and certificate.
        </li>
      </ol>
      <a
        href={SUPPLIERS}
        target="_blank"
        rel="noreferrer"
        className="underline"
      >
        Local firms, connections and open questions for the council
      </a>
    </section>
  );
}

function ProductCard({
  product: p,
  busy,
  onPlace,
}: {
  product: Product;
  busy: boolean;
  onPlace: (product: Product) => void;
}) {
  return (
    <li className="rounded border border-zinc-200 p-3 text-sm dark:border-zinc-800">
      <a
        href={p.url}
        target="_blank"
        rel="noreferrer"
        className="font-medium underline"
      >
        {p.supplier} {p.model}
      </a>
      <p>
        {p.lengthM} × {p.widthM} m · {p.floorAreaM2} m² ({p.areaBasis}) ·{" "}
        {p.bedrooms} bed, {p.bathrooms} bath · {p.type}
      </p>
      <p>
        {p.priceNzd === null
          ? `Price not published (${p.priceBasis})`
          : `${PRICE.format(p.priceNzd)} (${p.priceBasis})`}
      </p>
      <p>Excludes: {p.excludes}</p>
      <p>West Coast: {p.westCoast}</p>
      {p.placeable ? (
        <PlaceButton product={p} busy={busy} onPlace={onPlace} />
      ) : (
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          Can&apos;t be placed: its plan isn&apos;t the rectangle its figures
          give.
        </p>
      )}
    </li>
  );
}

function PlaceButton({
  product: p,
  busy,
  onPlace,
}: {
  product: Product;
  busy: boolean;
  onPlace: (product: Product) => void;
}) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => onPlace(p)}
      aria-label={`Place the ${p.supplier} ${p.model} on the site`}
      className="mt-2 rounded border border-zinc-300 px-3 py-1 disabled:opacity-40 dark:border-zinc-700"
    >
      Place it on the site
    </button>
  );
}
