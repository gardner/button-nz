import { describe, expect, it } from "vitest";

import { PRODUCTS } from "./fixtures";
import { parseProducts } from "./products";

describe("parseProducts", () => {
  it("reads the fitting and the unchecked products", () => {
    const found = parseProducts(PRODUCTS);
    expect(found.footprintM2).toBe(65);
    expect(found.fits.map((p) => p.model)).toEqual(["Vista", "Nile"]);
    expect(found.fits[0]).toMatchObject({
      lengthM: 12.2,
      widthM: 4,
      priceNzd: 190000,
      sources: [
        "https://www.airhome.co.nz/airhome-vista/",
        "https://www.airhome.co.nz/faq/",
      ],
    });
    expect(found.fits[1].priceNzd).toBeNull(); // not published: never a guess
    expect(found.unchecked.map((p) => p.model)).toEqual(["Nook 60"]);
  });

  it("refuses a link that isn't https", () => {
    const bad = structuredClone(PRODUCTS);
    bad.fits[0].url = "javascript:alert(1)";
    expect(() => parseProducts(bad)).toThrow(/https/);
  });

  it("refuses a product without its price basis", () => {
    const bad: Record<string, unknown> = structuredClone(PRODUCTS);
    delete (bad.fits as Record<string, unknown>[])[0].price_basis;
    expect(() => parseProducts(bad)).toThrow(/price_basis/);
  });
});
