interface Env {
  CF_ACCESS_CLIENT_ID: string;
  CF_ACCESS_CLIENT_SECRET: string;
  STAGING_PASSWORD: string;
}

const ORIGIN = "https://staging.blotter.fm";

function corsHeaders(): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

function unauthorized(): Response {
  return new Response("Unauthorized", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Staging"',
      ...corsHeaders(),
    },
  });
}

function checkAuth(request: Request, env: Env): boolean {
  const auth = request.headers.get("Authorization");
  if (!auth?.startsWith("Basic ")) return false;
  const decoded = atob(auth.slice(6));
  const [, password] = decoded.split(":");
  return password === env.STAGING_PASSWORD;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (!checkAuth(request, env)) {
      return unauthorized();
    }

    const url = new URL(request.url);
    url.hostname = "staging.blotter-dx8.pages.dev";
    const headers = new Headers(request.headers);
    headers.set("CF-Access-Client-Id", env.CF_ACCESS_CLIENT_ID);
    headers.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);

    const resp = await fetch(new Request(url, { method: request.method, headers, body: request.body }));
    const newResp = new Response(resp.body, resp);
    for (const [k, v] of Object.entries(corsHeaders())) {
      newResp.headers.set(k, v);
    }
    return newResp;
  },
};
