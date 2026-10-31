// @vitest-environment node
import { NextRequest } from "next/server";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { describe, expect, it } from "vitest";

import { config } from "../proxy";
import { ACCESS_COOKIE, admit } from "./access";

const CODE = "reefton-2026";

function request(path: string, cookie?: string): NextRequest {
  const headers = cookie ? { cookie: `${ACCESS_COOKIE}=${cookie}` } : undefined;
  return new NextRequest(new URL(path, "https://button.example"), { headers });
}

describe("admit", () => {
  it("lets everything through when no access code is set", () => {
    const response = admit(request("/api/designs"), undefined);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("turns a link with the code into a cookie, and drops the code from the URL", () => {
    const response = admit(request(`/?design=abc&code=${CODE}`), CODE);
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://button.example/?design=abc",
    );
    const cookie = response.cookies.get(ACCESS_COOKIE);
    expect(cookie?.value).toBe(CODE);
    expect(cookie).toMatchObject({
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
    });
  });

  it("lets a request holding the code through, pages and API alike", () => {
    for (const path of ["/", "/api/designs/abc"]) {
      const response = admit(request(path, CODE), CODE);
      expect(response.headers.get("x-middleware-next")).toBe("1");
    }
  });

  it("refuses a request without the code, or with the wrong one", async () => {
    for (const [path, cookie] of [
      ["/", undefined],
      ["/api/site", "guess"],
      ["/?code=guess", undefined],
    ] as const) {
      const response = admit(request(path, cookie), CODE);
      expect(response.status).toBe(401);
      expect(response.cookies.get(ACCESS_COOKIE)).toBeUndefined();
      expect(await response.text()).toMatch(/needs an access code/);
    }
  });
});

describe("the proxy", () => {
  it("gates everything but Next's static files, the image optimizer included", () => {
    const runs = (url: string) =>
      unstable_doesMiddlewareMatch({ config, nextConfig: {}, url });
    expect(runs("/")).toBe(true);
    expect(runs("/api/site/aerial.png")).toBe(true);
    expect(runs("/_next/image?url=%2Fapi%2Fsite%2Faerial.png&w=640&q=75")).toBe(
      true,
    );
    expect(runs("/_next/static/chunks/main.js")).toBe(false);
  });
});
