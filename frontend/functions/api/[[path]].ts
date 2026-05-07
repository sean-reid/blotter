interface Env {
  BACKEND_URL: string;
  CF_ACCESS_CLIENT_ID: string;
  CF_ACCESS_CLIENT_SECRET: string;
  ALLOWED_ORIGINS?: string;
}

function getAllowedOrigin(request: Request, env: Env): string {
  const origin = request.headers.get("Origin") || "";
  const allowed = env.ALLOWED_ORIGINS
    ? env.ALLOWED_ORIGINS.split(",").map((s) => s.trim())
    : [];
  if (allowed.length === 0) return origin || "*";
  return allowed.includes(origin) ? origin : allowed[0];
}

function corsHeaders(request: Request, env: Env): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": getAllowedOrigin(request, env),
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { env, request } = context;
  const headers = corsHeaders(request, env);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }

  const url = new URL(request.url);
  const backendUrl = new URL(url.pathname + url.search, env.BACKEND_URL);

  const resp = await fetch(backendUrl.toString(), {
    method: request.method,
    headers: {
      "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
      "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
    },
  });

  const body = await resp.text();
  return new Response(body, {
    status: resp.status,
    headers: {
      ...headers,
      "Content-Type": resp.headers.get("Content-Type") || "application/json",
      "Cache-Control": "no-store",
    },
  });
};
