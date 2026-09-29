// Serves the single static page the daily job writes to KV.
// The HTML is generated in Python. This Worker does not call a model
// or BigQuery, so a page view stays inside the Workers free request cap.
//
// PUT /publish replaces that page. The daily job sends the bearer secret
// PUBLISH_TOKEN. A normal visit never takes that branch.

const MAX_PAGE_BYTES = 2_000_000;

function authorized(request, secret) {
  if (!secret) return false;
  const header = request.headers.get("authorization") || "";
  const expected = `Bearer ${secret}`;
  const length = Math.max(header.length, expected.length);
  let mismatch = header.length === expected.length ? 0 : 1;
  for (let i = 0; i < length; i++) {
    const got = i < header.length ? header.charCodeAt(i) : 0;
    const want = i < expected.length ? expected.charCodeAt(i) : 0;
    mismatch |= got ^ want;
  }
  return mismatch === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "PUT" && url.pathname === "/publish") {
      if (!authorized(request, env.PUBLISH_TOKEN)) {
        return new Response("Unauthorized", {
          status: 401,
          headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
        });
      }
      const html = await request.text();
      const page = html.startsWith("<!DOCTYPE html>") && html.length <= MAX_PAGE_BYTES;
      if (!page) {
        return new Response("Rejected", {
          status: 400,
          headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
        });
      }
      await env.PAGE.put("index.html", html);
      return new Response("ok", {
        status: 200,
        headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
      });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", {
        status: 405,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    const html = await env.PAGE.get("index.html", "text");
    if (!html) {
      return new Response("The first session has not been published.", {
        status: 503,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    return new Response(html, {
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "no-cache",
      },
    });
  },
};
