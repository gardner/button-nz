import type { NextRequest } from "next/server";

import { admit } from "@/lib/access";

/** Every page and `/api` request needs the access code when the app is served
 * with BUTTON_ACCESS_CODE set (see lib/access.ts). Proxy runs before the
 * `/api` rewrite, so the API behind it is covered too. */
export function proxy(request: NextRequest) {
  return admit(request, process.env.BUTTON_ACCESS_CODE);
}

export const config = {
  // Next's own static files are the app's public code; everything else, the
  // image optimizer included (it can fetch /api), is gated.
  matcher: ["/((?!_next/static|favicon.ico).*)"],
};
