interface Env {
  CLICKHOUSE_URL: string;
  CLICKHOUSE_USER: string;
  CLICKHOUSE_PASSWORD: string;
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
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

const ALLOWED_TABLES = new Set([
  "blotter.scanner_events",
  "blotter.scanner_transcripts",
]);

const FORBIDDEN_PATTERN = /;\s*(?:INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|ATTACH|DETACH|RENAME|OPTIMIZE|SYSTEM|SET\b|KILL)/i;

function isReadOnly(sql: string): boolean {
  const trimmed = sql.replace(/\/\*[\s\S]*?\*\//g, "").replace(/--[^\n]*/g, "").trim();
  const first = trimmed.split(/\s+/)[0]?.toUpperCase();
  if (first !== "SELECT" && first !== "WITH") return false;
  if (FORBIDDEN_PATTERN.test(trimmed)) return false;
  return true;
}

export const onRequestOptions: PagesFunction<Env> = async (context) => {
  return new Response(null, { status: 204, headers: corsHeaders(context.request, context.env) });
};

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const { env, request } = context;
  const headers = corsHeaders(request, env);

  const sql = await request.text();
  if (!sql.trim()) {
    return new Response("Empty query", { status: 400, headers });
  }

  if (!isReadOnly(sql)) {
    return new Response("Only SELECT queries allowed", { status: 403, headers });
  }

  const url = new URL(env.CLICKHOUSE_URL);
  url.searchParams.set("default_format", "JSONEachRow");

  const incomingUrl = new URL(request.url);
  for (const [key, value] of incomingUrl.searchParams.entries()) {
    if (key.startsWith("param_")) {
      url.searchParams.set(key, value);
    }
  }

  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: {
      "Content-Type": "text/plain",
      "X-ClickHouse-User": env.CLICKHOUSE_USER,
      "X-ClickHouse-Key": env.CLICKHOUSE_PASSWORD,
      "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
      "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
    },
    body: sql,
  });

  const body = await resp.text();
  return new Response(body, {
    status: resp.status,
    headers: {
      ...headers,
      "Content-Type": resp.headers.get("Content-Type") || "text/plain",
    },
  });
};
