import { timingSafeEqual } from "node:crypto";

import { NextResponse, type NextRequest } from "next/server";

/** The cookie that holds the access code once a link with it was opened. */
export const ACCESS_COOKIE = "button_access";
const THIRTY_DAYS_S = 30 * 24 * 3600;

const REFUSED = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Button NZ</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 36rem; margin: 4rem auto">
<h1>Button NZ</h1>
<p>This demo needs an access code. Open it with the link you were given.</p>
</body></html>`;

/** Whether a request may reach the app when it is served with access `code`.
 * With no code, everything may: the app is running only for its team. A link
 * with `?code=` sets the cookie and goes on to the same page without it. Every
 * page and API request needs the cookie; anything else gets a 401 page. */
export function admit(request: NextRequest, code: string | undefined) {
  if (!code) return NextResponse.next();
  const offered = request.nextUrl.searchParams.get("code");
  if (offered !== null && matches(offered, code)) {
    const clean = request.nextUrl.clone();
    clean.searchParams.delete("code");
    const response = NextResponse.redirect(clean);
    response.cookies.set(ACCESS_COOKIE, code, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: THIRTY_DAYS_S,
    });
    return response;
  }
  const held = request.cookies.get(ACCESS_COOKIE)?.value;
  if (held !== undefined && matches(held, code)) return NextResponse.next();
  return new NextResponse(REFUSED, {
    status: 401,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

/** Compared in constant time, so the code can't be guessed a character at a time. */
function matches(offered: string, code: string): boolean {
  const a = Buffer.from(offered);
  const b = Buffer.from(code);
  return a.length === b.length && timingSafeEqual(a, b);
}
