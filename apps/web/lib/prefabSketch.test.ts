import { describe, expect, it } from "vitest";

import { PRODUCTS } from "./fixtures";
import { type Sketched, sketch, sketchScale } from "./prefabSketch";
import { type Product, parseProducts } from "./products";

const [VISTA, NILE] = parseProducts(PRODUCTS).fits; // 12.2 × 4 mono; 12 × 3.5 gable
const [NOOK] = parseProducts(PRODUCTS).unchecked; // figures not labelled

function drawn(product: Product, scale = sketchScale([product])): Sketched {
  const found = sketch(product, scale);
  if (!("faces" in found)) throw new Error(`no sketch: ${found.missing}`);
  return found;
}

function across(s: Sketched): number {
  const xs = s.faces.flatMap((f) => f.points.map(([x]) => x));
  return Math.max(...xs) - Math.min(...xs);
}

describe("a prefab's sketch", () => {
  it("draws every product to the same scale, so a longer one is drawn longer", () => {
    const long: Product = { ...VISTA, lengthM: 16.6, widthM: 4.2 };
    const scale = sketchScale([VISTA, long]);
    expect(across(drawn(long, scale))).toBeGreaterThan(
      across(drawn(VISTA, scale)) * 1.2,
    );
    expect(across(drawn(long, scale))).toBeLessThanOrEqual(scale.width);
  });

  it("sets its scale by the products it draws, not those it can't", () => {
    const huge: Product = { ...NOOK, lengthM: 40, widthM: 20 }; // not a footprint
    expect(sketchScale([VISTA, huge])).toEqual(sketchScale([VISTA]));
  });

  it("draws the roof form shown first, with the others in its description", () => {
    const nile = drawn(NILE);
    expect(nile.roof).toBe("gable");
    expect(nile.description).toBe(
      "Sketch of the Nile: 12 × 3.5 m, gable roof (or mono)",
    );
    expect(nile.faces.filter((f) => f.part === "roof")).toHaveLength(2);
    expect(drawn(VISTA).faces.filter((f) => f.part === "roof")).toHaveLength(1);
    const hip = drawn({
      ...VISTA,
      appearance: { ...VISTA.appearance, roofForms: ["hip"] },
    });
    expect(hip.faces.filter((f) => f.part === "roof")).toHaveLength(4);
    const flat = drawn({
      ...VISTA,
      appearance: { ...VISTA.appearance, roofForms: ["flat"] },
    });
    expect(flat.faces.filter((f) => f.part === "roof")).toHaveLength(1);
  });

  it("draws every slope of a square hip roof, whose ridge is a point", () => {
    const square = drawn({
      ...VISTA,
      lengthM: 7.2,
      widthM: 7.2,
      appearance: { ...VISTA.appearance, roofForms: ["hip"] },
    });
    expect(square.faces.filter((f) => f.part === "roof")).toHaveLength(4);
  });

  it("hides a slope turned away from the viewer", () => {
    const steep = drawn({
      ...NILE,
      appearance: { ...NILE.appearance, roofPitchDeg: 50 }, // as published
    });
    expect(steep.faces.filter((f) => f.part === "roof")).toHaveLength(1);
    expect(steep.faces.filter((f) => f.part === "walls")).toHaveLength(2);
  });

  it("paints the walls and roof in the product's colours, shaded by side", () => {
    const fills = (part: string) =>
      new Set(
        drawn(NILE)
          .faces.filter((f) => f.part === part)
          .map((f) => f.fill),
      );
    expect(fills("walls")).toContain("#f2f1ec");
    expect(fills("walls").size).toBe(2); // its side and its end, lit apart
    expect([...fills("roof")].every((c) => c !== "#f2f1ec")).toBe(true);
  });

  it("raises a mono roof higher than its walls on one side only", () => {
    const vista = drawn(VISTA);
    const top = (part: string) =>
      Math.min(
        ...vista.faces
          .filter((f) => f.part === part)
          .flatMap((f) => f.points.map(([, y]) => y)),
      );
    expect(top("roof")).toBeLessThan(top("walls") + 1e-9);
  });

  it("isn't drawn where the footprint isn't known", () => {
    expect(sketch(NOOK, sketchScale([NOOK]))).toEqual({
      missing: "its figures aren't a published footprint",
    });
  });

  it("isn't drawn where its roof isn't published", () => {
    const unknown: Product = {
      ...VISTA,
      appearance: { ...VISTA.appearance, roofForms: [] },
    };
    expect(sketch(unknown, sketchScale([unknown]))).toEqual({
      missing: "its roof isn't published",
    });
  });

  it("is the same every time", () => {
    expect(drawn(NILE)).toEqual(drawn(NILE));
  });
});
