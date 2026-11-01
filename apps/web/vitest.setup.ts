import { configure } from "@testing-library/dom";
import { afterEach } from "vitest";

// A shared CI runner can take more than testing-library's default second to
// render a page after its fetches answer: findBy* and waitFor wait 5 s
// before failing (a passing test still answers as soon as it can).
configure({ asyncUtilTimeout: 5000 });

// The design panel keeps the design on show in the address bar (?design=),
// and reads it when it mounts: start each test at a page with no link. Tests
// in the node environment (lib/access.test.ts) have no window.
afterEach(() => {
  if (typeof window !== "undefined") window.history.replaceState(null, "", "/");
});
