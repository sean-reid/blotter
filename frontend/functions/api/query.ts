interface Env {
  CLICKHOUSE_URL: string;
  CLICKHOUSE_USER: string;
  CLICKHOUSE_PASSWORD: string;
}

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function isReadOnly(sql: string): boolean {
  const trimmed = sql.replace(/\/\*[\s\S]*?\*\//g, "").trim();
  const first = trimmed.split(/\s+/)[0]?.toUpperCase();
  return first === "SELECT" || first === "WITH" || first === "SHOW" || first === "DESCRIBE";
}

export const onRequestOptions: PagesFunction<Env> = async () => {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
};

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const { env, request } = context;

  const sql = await request.text();
  if (!sql.trim()) {
    return new Response("Empty query", { status: 400, headers: CORS_HEADERS });
  }

  if (!isReadOnly(sql)) {
    return new Response("Only SELECT queries allowed", {
      status: 403,
      headers: CORS_HEADERS,
    });
  }

  const url = new URL(env.CLICKHOUSE_URL);
  url.searchParams.set("default_format", "JSONEachRow");

  const resp = await fetch(url.toString(), {
    method: "POST",
    headers: {
      "Content-Type": "text/plain",
      "X-ClickHouse-User": env.CLICKHOUSE_USER,
      "X-ClickHouse-Key": env.CLICKHOUSE_PASSWORD,
    },
    body: sql,
  });

  const body = await resp.text();
  return new Response(body, {
    status: resp.status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": resp.headers.get("Content-Type") || "text/plain",
    },
  });
};
