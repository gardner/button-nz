import { afterEach } from "vitest";

// The design panel keeps the design on show in the address bar (?design=),
// and reads it when it mounts: start each test at a page with no link. Tests
// in the node environment (lib/access.test.ts) have no window.
afterEach(() => {
  if (typeof window !== "undefined") window.history.replaceState(null, "", "/");
});
