import { describe, expect, it } from "vitest";

import nextConfig from "./next.config";

describe("next.config", () => {
  it("sends the old /explore to the home page (Next keeps the query)", async () => {
    expect(await nextConfig.redirects?.()).toContainEqual({
      source: "/explore",
      destination: "/",
      permanent: true,
    });
  });
});
