import type { Source } from "./api";

/** A licence as people read it: "CC-BY-4.0" is "CC BY 4.0"; anything else
 * (a source that states none) is said as its source says it. */
function licenceOf(licence: string): string {
  return licence.startsWith("CC-")
    ? licence.replaceAll("-", " ")
    : `licence ${licence}`;
}

const ENTITIES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Words made safe for HTML: MapLibre puts a source's attribution in the
 * page as markup (so a credit can carry a link), and a site's sources are
 * words from LINZ's catalogues, not ours. */
function escaped(words: string): string {
  return words.replace(/[&<>"']/g, (c) => ENTITIES[c]);
}

/** The map's credit for a site's own data, which CC BY asks for wherever it
 * is shown: each provider once, after the works of theirs used, with the
 * licence. None for a site with no sources. */
export function creditOf(sources: Source[]): string | undefined {
  const works = new Map<string, string[]>(); // "provider, licence" -> titles
  for (const source of sources) {
    const by = escaped(`${source.attribution}, ${licenceOf(source.licence)}`);
    works.set(by, [...(works.get(by) ?? []), escaped(source.title)]);
  }
  if (works.size === 0) return undefined;
  const credits = [...works].map(
    ([by, titles]) => `${titles.join(", ")}: ${by}`,
  );
  return creditLines(["This site:", ...credits]);
}

/** A source's credit for the map, each line (HTML) on its own, all in one
 * element: the map's credits box hides words outside one (MapLibre's ` | `
 * between sources, see globals.css), so every credit must be inside. */
export function creditLines(lines: string[]): string {
  const shown = lines.map((line) => `<p>${line}</p>`).join("");
  return `<div class="map-credits">${shown}</div>`;
}
