// Serves the single static page the daily job writes to KV.
// The HTML is generated in Python. This Worker does not call a model
// or BigQuery, so a page view stays inside the Workers free request cap.
export default {
  async fetch(_request, env) {
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
